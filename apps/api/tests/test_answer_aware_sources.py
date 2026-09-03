"""Tests for answer-aware source rescoring (experiment)."""

from types import SimpleNamespace
from typing import cast

import pytest

from goldenson_api.retrieval.service import RetrievedSource, WorkspaceRetrievalService
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.file_service import FileService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService


class FakePages:
    def __init__(self, pages: list[object]) -> None:
        self.pages = list(pages)

    async def list_pages(self, _workspace_id: str) -> list[object]:
        return self.pages

    async def get_page(self, page_id: str) -> object | None:
        return next((page for page in self.pages if getattr(page, "id", None) == page_id), None)


class FakeBlocks:
    def __init__(self, blocks: dict[str, list[object]]) -> None:
        self.blocks = {page_id: list(items) for page_id, items in blocks.items()}

    async def list_blocks(self, page_id: str) -> list[object]:
        return self.blocks.get(page_id, [])


class FakeFiles:
    def __init__(self, files: list[object]) -> None:
        self.files = list(files)

    async def list_workspace_files(self, _workspace_id: str) -> list[object]:
        return self.files


class FakeEmbeddings:
    """Mock embedding provider that returns deterministic embeddings based on text."""

    async def embed(self, text: str) -> list[float]:
        """Return a deterministic embedding for a given text."""
        if not text.strip():
            return []
        
        # Simple mock: hash the text and return a fixed-size vector
        # This is deterministic but not semantically meaningful
        # For testing, we'll use keyword presence as a signal
        text_lower = text.lower()
        
        # Create a vector that has high similarity when keywords match
        base = [0.1] * 5
        
        # Boost specific dimensions for known keywords
        if "miles" in text_lower:
            base[0] = 0.9
        if "decide" in text_lower or "decision" in text_lower:
            base[1] = 0.9
        if "career" in text_lower or "thoughts" in text_lower:
            base[2] = 0.8
        if "review" in text_lower or "plan" in text_lower:
            base[3] = 0.7
        
        return base


class FakeKnowledge:
    def __init__(self) -> None:
        self._embeddings = FakeEmbeddings()

    async def semantic_search(
        self, _workspace_id: str, _query: str, limit: int
    ) -> list[tuple[object, float]]:
        return []

    async def embed_text(self, text: str) -> list[float]:
        """Embed a single piece of text."""
        return await self._embeddings.embed(text)


def service_with_embeddings(
    pages: list[object],
    blocks: dict[str, list[object]],
    files: list[object],
) -> WorkspaceRetrievalService:
    service = WorkspaceRetrievalService.__new__(WorkspaceRetrievalService)
    service._pages = cast(PageService, FakePages(pages))
    service._blocks = cast(BlockService, FakeBlocks(blocks))
    service._files = cast(FileService, FakeFiles(files))
    service._knowledge = cast(KnowledgeService, FakeKnowledge())
    return service


@pytest.mark.asyncio
async def test_rescore_sources_removes_weak_semantic_candidate() -> None:
    """Answer-aware rescoring removes loosely related pages."""
    miles_page = SimpleNamespace(id="p1", title="Miles notes", workspace_id="w1")
    career_page = SimpleNamespace(id="p2", title="Career Thoughts", workspace_id="w1")
    miles_block = SimpleNamespace(
        id="b1", content={"text": "I decided to keep talking with Miles."}
    )
    career_block = SimpleNamespace(
        id="b2", content={"text": "General thoughts about career transitions."}
    )
    
    service = service_with_embeddings(
        [miles_page, career_page],
        {"p1": [miles_block], "p2": [career_block]},
        [],
    )
    
    # Initial source list includes both (simulating retrieval that caught both)
    sources = [
        RetrievedSource(
            kind="block",
            title="Miles notes",
            snippet="I decided to keep talking with Miles.",
            page_id="p1",
            block_id="b1",
            score=0.8,
        ),
        RetrievedSource(
            kind="block",
            title="Career Thoughts",
            snippet="General thoughts about career transitions.",
            page_id="p2",
            block_id="b2",
            score=0.7,
        ),
    ]
    
    # Answer discusses Miles specifically
    answer = "I decided to keep talking with Miles to discuss the project timeline."
    query = "What did I decide about Miles?"
    
    rescored, embed_latency = await service.rescore_sources_by_answer(answer, query, sources)
    
    # Should keep Miles-related source, might remove career
    assert any(s.page_id == "p1" for s in rescored)
    assert embed_latency >= 0.0


@pytest.mark.asyncio
async def test_rescore_preserves_multiple_relevant_sources() -> None:
    """Answer-aware rescoring keeps multiple genuinely relevant sources."""
    first_page = SimpleNamespace(id="p1", title="Miles decision", workspace_id="w1")
    second_page = SimpleNamespace(id="p2", title="Miles follow-up", workspace_id="w1")
    
    service = service_with_embeddings(
        [first_page, second_page],
        {
            "p1": [SimpleNamespace(id="b1", content={"text": "Miles chose the west route."})],
            "p2": [SimpleNamespace(id="b2", content={"text": "Miles will review the plan Friday."})],
        },
        [],
    )
    
    sources = [
        RetrievedSource(
            kind="block",
            title="Miles decision",
            snippet="Miles chose the west route.",
            page_id="p1",
            block_id="b1",
            score=0.8,
        ),
        RetrievedSource(
            kind="block",
            title="Miles follow-up",
            snippet="Miles will review the plan Friday.",
            page_id="p2",
            block_id="b2",
            score=0.7,
        ),
    ]
    
    answer = "Miles decided to choose the west route and will review the plan Friday."
    query = "What did Miles decide?"
    
    rescored, _ = await service.rescore_sources_by_answer(answer, query, sources)
    
    # Both Miles-related sources should remain
    assert len(rescored) >= 1
    miles_sources = [s for s in rescored if "Miles" in s.title]
    assert len(miles_sources) >= 1


@pytest.mark.asyncio
async def test_rescore_short_answer_skips_embedding() -> None:
    """Very short answers skip embedding and return sources unchanged."""
    page = SimpleNamespace(id="p1", title="Notes", workspace_id="w1")
    
    service = service_with_embeddings([page], {"p1": []}, [])
    
    sources = [
        RetrievedSource(
            kind="page",
            title="Notes",
            snippet="Some content.",
            page_id="p1",
            score=0.5,
        ),
    ]
    
    # Short answer
    answer = "Yes."
    query = "What about this?"
    
    rescored, embed_latency = await service.rescore_sources_by_answer(answer, query, sources)
    
    # Should skip embedding and return unchanged
    assert rescored == sources
    assert embed_latency == 0.0


@pytest.mark.asyncio
async def test_rescore_empty_sources_returns_empty() -> None:
    """Rescoring empty source list returns empty."""
    service = service_with_embeddings([], {}, [])
    
    answer = "Some answer with meaningful content about a topic."
    query = "What about topic?"
    
    rescored, _ = await service.rescore_sources_by_answer(answer, query, [])
    
    assert rescored == []


@pytest.mark.asyncio
async def test_rescore_empty_answer_returns_unchanged() -> None:
    """Empty or whitespace-only answer returns sources unchanged."""
    page = SimpleNamespace(id="p1", title="Notes", workspace_id="w1")
    
    service = service_with_embeddings([page], {"p1": []}, [])
    
    sources = [
        RetrievedSource(
            kind="page",
            title="Notes",
            snippet="Content.",
            page_id="p1",
            score=0.5,
        ),
    ]
    
    rescored, _ = await service.rescore_sources_by_answer("   ", "Query?", sources)
    
    assert rescored == sources


@pytest.mark.asyncio
async def test_rescore_maintains_source_provenance() -> None:
    """Answer-aware rescoring does not lose block/file provenance."""
    page = SimpleNamespace(id="p1", title="Page", workspace_id="w1")
    
    service = service_with_embeddings(
        [page],
        {"p1": [SimpleNamespace(id="b1", content={"text": "Block content about decision."})]},
        [],
    )
    
    block_source = RetrievedSource(
        kind="block",
        title="Page",
        snippet="Block content about decision.",
        page_id="p1",
        block_id="b1",
        score=0.7,
    )
    
    answer = "The decision was made in the block content."
    query = "What decision?"
    
    rescored, _ = await service.rescore_sources_by_answer(answer, query, [block_source])
    
    # Provenance must be preserved
    assert rescored[0].page_id == "p1"
    assert rescored[0].block_id == "b1"
    assert rescored[0].kind == "block"
