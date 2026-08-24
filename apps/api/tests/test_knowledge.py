from __future__ import annotations

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.knowledge import PageKnowledge
from goldenson_api.db.models.knowledge_chunk import KnowledgeChunk
from goldenson_api.schemas.block import BlockCreate, BlockUpdate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


class FakeEmbeddingProvider:
    model = "test-embedding"
    version = "test-v1"
    dimensions = 3

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_on = fail_on

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        if self.fail_on is not None and self.fail_on in text:
            raise RuntimeError("embedding failed")
        return [float(len(text)), 1.0 if "local" in text else 0.0, 1.0]


async def make_page(session: AsyncSession) -> tuple[str, str, str]:
    workspace = await WorkspaceService(session).create_workspace(WorkspaceCreate(name="Knowledge"))
    page = await PageService(session).create_page(
        PageCreate(workspace_id=workspace.id, title="Local AI", position=0)
    )
    block = await BlockService(session).create_block(
        BlockCreate(
            page_id=page.id,
            type="paragraph",
            position=0,
            content={"text": "local inference with Ollama"},
        )
    )
    await session.commit()
    return workspace.id, page.id, block.id


async def chunk_rows(session: AsyncSession, page_id: str) -> list[KnowledgeChunk]:
    result = await session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.page_id == page_id))
    return list(result)


async def test_index_persists_block_provenance_and_uses_sqlite_vec(
    session: AsyncSession,
) -> None:
    workspace_id, page_id, block_id = await make_page(session)
    provider = FakeEmbeddingProvider()
    service = KnowledgeService(session, provider)

    record = await service.index_page(page_id)
    await session.commit()
    chunks = await chunk_rows(session, page_id)

    assert record.status == "ready"
    assert any(chunk.block_id == block_id for chunk in chunks)
    results = await service.semantic_search(workspace_id, "local inference")
    assert results
    assert any(chunk.block_id == block_id for chunk, _ in results)
    assert await session.scalar(text("SELECT count(*) FROM vec_knowledge_chunks")) == len(chunks)


async def test_unchanged_content_is_not_reembedded_and_deleted_block_disappears(
    session: AsyncSession,
) -> None:
    workspace_id, page_id, block_id = await make_page(session)
    provider = FakeEmbeddingProvider()
    service = KnowledgeService(session, provider)

    await service.index_page(page_id)
    first_call_count = len(provider.calls)
    await session.commit()
    await service.index_page(page_id)
    assert len(provider.calls) == first_call_count

    await BlockService(session).delete_block(block_id)
    await session.commit()
    await service.index_page(page_id)
    await session.commit()
    chunks = await chunk_rows(session, page_id)
    assert all(chunk.block_id is None for chunk in chunks)
    results = await service.semantic_search(workspace_id, "Ollama")
    assert all(chunk.block_id is None for chunk, _ in results)


async def test_failed_index_is_observable_without_partial_new_vectors(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id, page_id, _ = await make_page(session)
    provider = FakeEmbeddingProvider(fail_on="local")
    service = KnowledgeService(session, provider)
    warnings: list[tuple[object, ...]] = []
    monkeypatch.setattr(
        "goldenson_api.services.knowledge_service.logger.warning",
        lambda *arguments: warnings.append(arguments),
    )

    record = await service.index_page(page_id)
    await session.commit()

    assert record.status == "failed"
    assert record.error == "Content indexing could not be completed."
    assert await service.semantic_search(workspace_id, "local") == []
    assert warnings
    assert "semantic search unavailable; using lexical results" in str(warnings[0][0])


async def test_retry_succeeds_after_transient_embedding_failure(
    session: AsyncSession,
) -> None:
    workspace_id, page_id, _ = await make_page(session)
    provider = FakeEmbeddingProvider(fail_on="local")
    service = KnowledgeService(session, provider)

    failed = await service.index_page(page_id)
    assert failed.status == "failed"
    provider.fail_on = None
    recovered = await service.index_page(page_id)
    await session.commit()

    assert recovered.status == "ready"
    assert await service.semantic_search(workspace_id, "local")


async def test_failed_reindex_preserves_previous_valid_index(
    session: AsyncSession,
) -> None:
    workspace_id, page_id, _ = await make_page(session)
    first_provider = FakeEmbeddingProvider()
    await KnowledgeService(session, first_provider).index_page(page_id)
    await session.commit()
    original_chunk_ids = {chunk.id for chunk in await chunk_rows(session, page_id)}

    unavailable_provider = FakeEmbeddingProvider(fail_on="local")
    unavailable_provider.version = "test-v2"
    failed = await KnowledgeService(session, unavailable_provider).index_page(page_id)
    await session.commit()

    preserved_chunks = await chunk_rows(session, page_id)
    assert failed.status == "failed"
    assert {chunk.id for chunk in preserved_chunks} == original_chunk_ids
    assert all(chunk.status == "ready" for chunk in preserved_chunks)
    assert await session.scalar(text("SELECT count(*) FROM vec_knowledge_chunks")) == len(
        preserved_chunks
    )
    assert await KnowledgeService(session, first_provider).semantic_search(workspace_id, "local")


async def test_stale_generation_cannot_overwrite_newer_index(
    session: AsyncSession,
) -> None:
    _, page_id, _ = await make_page(session)
    service = KnowledgeService(session, FakeEmbeddingProvider())
    await service.index_page(page_id)
    await session.commit()

    stale_generation = await service.mark_pending(page_id)
    current_generation = await service.mark_pending(page_id)
    current = await service.index_page(page_id, expected_generation=current_generation)
    stale = await service.index_page(page_id, expected_generation=stale_generation)
    await session.commit()

    assert current.status == "ready"
    assert stale.status == "ready"
    assert stale.generation == current_generation


async def test_embedding_configuration_change_reindexes_incompatible_chunks(
    session: AsyncSession,
) -> None:
    workspace_id, page_id, _ = await make_page(session)
    first_provider = FakeEmbeddingProvider()
    await KnowledgeService(session, first_provider).index_page(page_id)
    await session.commit()

    changed_provider = FakeEmbeddingProvider()
    changed_provider.version = "test-v2"
    record = await KnowledgeService(session, changed_provider).index_page(page_id)
    await session.commit()
    chunks = await chunk_rows(session, page_id)

    assert record.status == "ready"
    assert all(chunk.embedding_version == "test-v2" for chunk in chunks)
    assert all(chunk.status == "ready" and chunk.embedding_dimensions == 3 for chunk in chunks)
    assert await session.scalar(text("SELECT count(*) FROM vec_knowledge_chunks")) == len(chunks)
    assert await KnowledgeService(session, changed_provider).semantic_search(workspace_id, "local")


async def test_embedding_configuration_mismatch_marks_workspace_stale(
    session: AsyncSession,
) -> None:
    workspace_id, page_id, _ = await make_page(session)
    await KnowledgeService(session, FakeEmbeddingProvider()).index_page(page_id)
    await session.commit()

    changed_provider = FakeEmbeddingProvider()
    changed_provider.version = "test-v2"
    assert (
        await KnowledgeService(session, changed_provider).semantic_search(workspace_id, "local")
        == []
    )
    await session.commit()
    record = await session.scalar(select(PageKnowledge).where(PageKnowledge.page_id == page_id))

    assert record is not None
    assert record.status == "stale"


async def test_foreign_keys_are_enabled_for_application_engine(session: AsyncSession) -> None:
    assert await session.scalar(text("PRAGMA foreign_keys")) == 1


async def test_updated_block_replaces_old_indexed_content(session: AsyncSession) -> None:
    workspace_id, page_id, block_id = await make_page(session)
    provider = FakeEmbeddingProvider()
    service = KnowledgeService(session, provider)
    await service.index_page(page_id)
    await session.commit()

    block = await BlockService(session).get_block(block_id)
    assert block is not None
    await BlockService(session).update_block(
        block_id,
        BlockUpdate(
            version=block.version,
            content={"text": "completely unrelated replacement"},
        ),
    )
    await session.commit()
    await service.index_page(page_id)
    await session.commit()

    chunks = await chunk_rows(session, page_id)
    assert all("local inference" not in chunk.text for chunk in chunks)
    assert any("unrelated replacement" in chunk.text for chunk in chunks)
    results = await service.semantic_search(workspace_id, "local inference")
    assert all("local inference" not in chunk.text for chunk, _ in results)
