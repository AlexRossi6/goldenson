from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast

import pytest

from goldenson_api.retrieval.service import WorkspaceRetrievalService
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.file_service import FileService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService


class FakePages:
    def __init__(self, pages: Sequence[object]) -> None:
        self.pages = list(pages)

    async def list_pages(self, _workspace_id: str) -> list[object]:
        return self.pages


class FakeBlocks:
    def __init__(self, blocks: dict[str, Sequence[object]]) -> None:
        self.blocks = {page_id: list(items) for page_id, items in blocks.items()}

    async def list_blocks(self, page_id: str) -> list[object]:
        return self.blocks.get(page_id, [])


class FakeFiles:
    def __init__(self, files: Sequence[object]) -> None:
        self.files = list(files)

    async def list_workspace_files(self, _workspace_id: str) -> list[object]:
        return self.files


class FakeKnowledge:
    def __init__(self, semantic: Sequence[tuple[object, float]]) -> None:
        self.semantic = list(semantic)

    async def semantic_search(
        self, _workspace_id: str, _query: str, limit: int
    ) -> list[tuple[object, float]]:
        return self.semantic[:limit]


def service_with(
    pages: Sequence[object],
    blocks: dict[str, Sequence[object]],
    files: Sequence[object],
    semantic: Sequence[tuple[object, float]] = (),
) -> WorkspaceRetrievalService:
    service = WorkspaceRetrievalService.__new__(WorkspaceRetrievalService)
    service._pages = cast(PageService, FakePages(pages))
    service._blocks = cast(BlockService, FakeBlocks(blocks))
    service._files = cast(FileService, FakeFiles(files))
    service._knowledge = cast(KnowledgeService, FakeKnowledge(semantic))
    return service


@pytest.mark.asyncio
async def test_hybrid_search_preserves_sources_and_prioritizes_exact_title() -> None:
    exact = SimpleNamespace(id="p1", title="sqlite-vec", workspace_id="w1")
    semantic = SimpleNamespace(id="p2", title="Vector notes", workspace_id="w1")
    block = SimpleNamespace(id="b1", content={"text": "sqlite-vec setup"})
    file = SimpleNamespace(id="f1", name="sqlite-vec.md", page_id="p1")
    service = service_with(
        [exact, semantic],
        {"p1": [block], "p2": []},
        [file],
        [(SimpleNamespace(page_id="p2", block_id=None, text="semantic vector notes"), 0.95)],
    )

    result = await service.search("w1", "sqlite-vec", limit=5)

    assert result.sources[0].page_id == "p1"
    assert result.sources[0].kind == "page"
    assert any(source.block_id == "b1" for source in result.sources)
    assert any(source.file_id == "f1" for source in result.sources)
    assert "sqlite-vec" in result.context


@pytest.mark.asyncio
async def test_semantic_only_result_is_returned_without_lexical_overlap() -> None:
    page = SimpleNamespace(id="p1", title="Local experiments", workspace_id="w1")
    semantic_record = SimpleNamespace(page_id="p1", block_id=None, text="semantic content")
    service = service_with([page], {"p1": []}, [], [(semantic_record, 0.8)])

    result = await service.search("w1", "meaning query", limit=3)

    assert [(source.kind, source.page_id) for source in result.sources] == [("page", "p1")]


@pytest.mark.asyncio
async def test_empty_query_and_irrelevant_sources_are_excluded() -> None:
    page = SimpleNamespace(id="p1", title="Unrelated", workspace_id="w1")
    service = service_with([page], {"p1": []}, [])

    assert (await service.search("w1", "   ")).sources == []
    assert (await service.search("w1", "missing term")).sources == []


@pytest.mark.asyncio
async def test_equal_scores_are_deterministic() -> None:
    pages = [
        SimpleNamespace(id="p2", title="same", workspace_id="w1"),
        SimpleNamespace(id="p1", title="same", workspace_id="w1"),
    ]
    service = service_with(pages, {"p1": [], "p2": []}, [])

    result = await service.search("w1", "same", limit=5)

    assert [source.page_id for source in result.sources] == ["p1", "p2"]
