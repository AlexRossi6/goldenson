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

    async def get_page(self, page_id: str) -> object | None:
        return next((page for page in self.pages if getattr(page, "id", None) == page_id), None)


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
    assert result.sources[0].kind == "block"
    assert any(source.block_id == "b1" for source in result.sources)
    assert any(source.file_id == "f1" for source in result.sources)
    assert not any(source.kind == "page" and source.page_id == "p1" for source in result.sources)
    assert "sqlite-vec" in result.context


@pytest.mark.asyncio
async def test_exact_page_and_block_duplicate_prefers_block_provenance() -> None:
    page = SimpleNamespace(id="p1", title="Launch notes", workspace_id="w1")
    block = SimpleNamespace(id="b1", content={"text": "Starling launches in October."})
    service = service_with([page], {"p1": [block]}, [])

    result = await service.search("w1", "Starling launches October")

    assert [(source.kind, source.block_id) for source in result.sources] == [("block", "b1")]
    assert result.context.count("Starling launches in October.") == 1


@pytest.mark.asyncio
async def test_page_result_is_removed_when_a_different_block_contains_the_match() -> None:
    page = SimpleNamespace(id="p1", title="Launch notes", workspace_id="w1")
    block = SimpleNamespace(id="b1", content={"text": "Starling launches in October."})
    semantic_page = SimpleNamespace(page_id="p1", block_id=None, text="launch planning context")
    service = service_with([page], {"p1": [block]}, [], [(semantic_page, 0.9)])

    result = await service.search("w1", "Starling launches October")

    assert [(source.kind, source.block_id) for source in result.sources] == [("block", "b1")]


@pytest.mark.asyncio
async def test_distinct_matching_blocks_on_one_page_are_preserved() -> None:
    page = SimpleNamespace(id="p1", title="Launch notes", workspace_id="w1")
    blocks = [
        SimpleNamespace(id="b1", content={"text": "Starling launches in October."}),
        SimpleNamespace(id="b2", content={"text": "October launch review is scheduled Friday."}),
    ]
    service = service_with([page], {"p1": blocks}, [])

    result = await service.search("w1", "October launch", limit=5)

    assert {source.block_id for source in result.sources} == {"b1", "b2"}
    assert all(source.kind == "block" for source in result.sources)
    assert {source.snippet for source in result.sources} == {
        "Starling launches in October.",
        "October launch review is scheduled Friday.",
    }


@pytest.mark.asyncio
async def test_title_only_match_keeps_page_provenance() -> None:
    page = SimpleNamespace(id="p1", title="Kubernetes deployment", workspace_id="w1")
    service = service_with([page], {"p1": []}, [])

    result = await service.search("w1", "Kubernetes deployment")

    assert [(source.kind, source.page_id, source.block_id) for source in result.sources] == [
        ("page", "p1", None)
    ]


@pytest.mark.asyncio
async def test_duplicate_semantic_chunks_for_one_block_return_one_result() -> None:
    page = SimpleNamespace(id="p1", title="Launch notes", workspace_id="w1")
    block = SimpleNamespace(id="b1", content={"text": "Starling launches in October."})
    semantic_chunks = [
        (SimpleNamespace(page_id="p1", block_id="b1", text="Starling launches"), 0.9),
        (SimpleNamespace(page_id="p1", block_id="b1", text="launches in October"), 0.8),
    ]
    service = service_with([page], {"p1": [block]}, [], semantic_chunks)

    result = await service.search("w1", "Starling launches", limit=5)

    assert [source.block_id for source in result.sources] == ["b1"]


@pytest.mark.asyncio
async def test_lexical_fallback_remains_block_focused_without_embeddings() -> None:
    page = SimpleNamespace(id="p1", title="Launch notes", workspace_id="w1")
    block = SimpleNamespace(id="b1", content={"text": "Starling launches in October."})
    service = service_with([page], {"p1": [block]}, [], semantic=[])

    result = await service.search("w1", "Starling launches October")

    assert [(source.kind, source.block_id) for source in result.sources] == [("block", "b1")]


@pytest.mark.asyncio
async def test_semantic_only_result_is_returned_without_lexical_overlap() -> None:
    page = SimpleNamespace(id="p1", title="Local experiments", workspace_id="w1")
    semantic_record = SimpleNamespace(page_id="p1", block_id=None, text="semantic content")
    service = service_with([page], {"p1": []}, [], [(semantic_record, 0.8)])

    result = await service.search("w1", "meaning query", limit=3)

    assert [(source.kind, source.page_id) for source in result.sources] == [("page", "p1")]
    assert [(source.kind, source.page_id) for source in result.answer_sources or []] == [
        ("page", "p1")
    ]


@pytest.mark.asyncio
async def test_answer_sources_exclude_semantic_only_context_candidates() -> None:
    miles_page = SimpleNamespace(id="p1", title="Miles notes", workspace_id="w1")
    career_page = SimpleNamespace(id="p2", title="Thoughts", workspace_id="w1")
    miles_block = SimpleNamespace(
        id="b1", content={"text": "I decided to keep talking with Miles."}
    )
    semantic_thoughts = SimpleNamespace(
        page_id="p2", block_id=None, text="General career reflections"
    )
    service = service_with(
        [miles_page, career_page],
        {"p1": [miles_block], "p2": []},
        [],
        [(semantic_thoughts, 0.9)],
    )

    result = await service.search("w1", "What did I decide about Miles?", limit=5)

    assert {source.page_id for source in result.sources} == {"p1", "p2"}
    assert [(source.page_id, source.block_id) for source in result.answer_sources or []] == [
        ("p1", "b1")
    ]
    assert "General career reflections" in result.context
    assert result.answer_sources is not None
    assert result.answer_sources[0].block_id == miles_block.id


@pytest.mark.asyncio
async def test_answer_sources_preserve_multiple_lexical_evidence_pages() -> None:
    first_page = SimpleNamespace(id="p1", title="Miles decision", workspace_id="w1")
    second_page = SimpleNamespace(id="p2", title="Miles follow-up", workspace_id="w1")
    service = service_with(
        [first_page, second_page],
        {
            "p1": [SimpleNamespace(id="b1", content={"text": "Miles chose the west route."})],
            "p2": [
                SimpleNamespace(id="b2", content={"text": "Miles will review the plan Friday."})
            ],
        },
        [],
    )

    result = await service.search("w1", "What did I decide about Miles?", limit=5)

    assert {source.page_id for source in result.answer_sources or []} == {"p1", "p2"}
    assert {source.block_id for source in result.answer_sources or []} == {"b1", "b2"}


@pytest.mark.asyncio
async def test_empty_query_and_irrelevant_sources_are_excluded() -> None:
    page = SimpleNamespace(id="p1", title="Unrelated", workspace_id="w1")
    service = service_with([page], {"p1": []}, [])

    assert (await service.search("w1", "   ")).sources == []
    assert (await service.search("w1", "missing term")).sources == []


@pytest.mark.asyncio
async def test_question_words_do_not_create_irrelevant_lexical_evidence() -> None:
    page = SimpleNamespace(id="p1", title="Garden plan", workspace_id="w1")
    block = SimpleNamespace(id="b1", content={"text": "This is the spring planting schedule."})
    service = service_with([page], {"p1": [block]}, [])

    result = await service.search("w1", "How is Kubernetes deployed in the workspace?")

    assert result.sources == []
    assert result.context == ""


@pytest.mark.asyncio
async def test_weak_semantic_match_is_not_treated_as_workspace_evidence() -> None:
    page = SimpleNamespace(id="p1", title="Garden plan", workspace_id="w1")
    semantic_record = SimpleNamespace(page_id="p1", block_id=None, text="Spring planting")
    service = service_with([page], {"p1": []}, [], [(semantic_record, 0.2)])

    result = await service.search("w1", "Kubernetes deployment")

    assert result.sources == []


@pytest.mark.asyncio
async def test_equal_scores_are_deterministic() -> None:
    pages = [
        SimpleNamespace(id="p2", title="same", workspace_id="w1"),
        SimpleNamespace(id="p1", title="same", workspace_id="w1"),
    ]
    service = service_with(pages, {"p1": [], "p2": []}, [])

    result = await service.search("w1", "same", limit=5)

    assert [source.page_id for source in result.sources] == ["p1", "p2"]


@pytest.mark.asyncio
async def test_searchable_text_file_matches_extracted_content() -> None:
    file = SimpleNamespace(
        id="f1",
        name="notes.md",
        page_id=None,
        search_text="local inference benchmark results",
    )
    service = service_with([], {}, [file])

    result = await service.search("w1", "benchmark results")

    assert len(result.sources) == 1
    assert result.sources[0].file_id == "f1"
    assert result.sources[0].snippet == "local inference benchmark results"


@pytest.mark.asyncio
async def test_unparsed_file_remains_searchable_by_filename_metadata() -> None:
    file = SimpleNamespace(
        id="f1",
        name="Alex_Rossi_FlowCV_Resume_2026-08-15.pdf",
        page_id=None,
        search_text=None,
    )
    service = service_with([], {}, [file])

    result = await service.search("w1", "FlowCV Resume")

    assert len(result.sources) == 1
    assert result.sources[0].file_id == "f1"
    assert result.sources[0].snippet == file.name


@pytest.mark.asyncio
async def test_related_content_uses_lexical_evidence_and_filters_weak_duplicates() -> None:
    current = SimpleNamespace(id="p0", title="Private Ollama deployment", workspace_id="w1")
    related = SimpleNamespace(id="p1", title="Local model operations", workspace_id="w1")
    weak = SimpleNamespace(id="p2", title="Private garden notes", workspace_id="w1")
    related_block = SimpleNamespace(
        id="b1",
        content={"text": "Ollama serves private local inference models on localhost."},
    )
    service = service_with(
        [current, related, weak],
        {
            "p0": [
                SimpleNamespace(
                    id="b0",
                    content={"text": "Run private Ollama models for local inference on localhost."},
                )
            ],
            "p1": [related_block],
            "p2": [SimpleNamespace(id="b2", content={"text": "Private tomato harvest."})],
        },
        [],
    )

    result = await service.related("p0")

    assert len(result.items) == 1
    assert result.items[0].page_id == "p1"
    assert result.items[0].block_id == "b1"
    assert result.items[0].snippet == related_block.content["text"]


@pytest.mark.asyncio
async def test_related_content_includes_strong_semantic_evidence_without_word_overlap() -> None:
    current = SimpleNamespace(id="p0", title="Canine training journal", workspace_id="w1")
    related = SimpleNamespace(id="p1", title="Companion behavior notes", workspace_id="w1")
    semantic_chunk = SimpleNamespace(
        page_id="p1",
        block_id="b1",
        text="Positive reinforcement routines for household pets.",
    )
    service = service_with(
        [current, related],
        {
            "p0": [SimpleNamespace(id="b0", content={"text": "Daily puppy obedience work."})],
            "p1": [SimpleNamespace(id="b1", content={"text": semantic_chunk.text})],
        },
        [],
        [(semantic_chunk, 0.82)],
    )

    result = await service.related("p0")

    assert [(item.page_id, item.block_id) for item in result.items] == [("p1", "b1")]
    assert result.items[0].snippet == semantic_chunk.text
