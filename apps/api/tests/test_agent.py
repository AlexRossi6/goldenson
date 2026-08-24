from __future__ import annotations

import asyncio
import io
import json
from collections.abc import AsyncIterator, Sequence
from typing import cast

import anyio
import httpx
import pytest
from fastapi import FastAPI, UploadFile
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from goldenson_api.agent.service import (
    AgentService,
    cancel_agent_run,
    cancel_persisted_agent_run,
)
from goldenson_api.agent.tools import AgentToolExecutor, validate_tool_arguments
from goldenson_api.api.agent import get_llm_provider
from goldenson_api.db.repositories.agent_audit_repository import AgentAuditRepository
from goldenson_api.inference.provider import (
    ChatMessage,
    LLMProviderTimeoutError,
    LLMResponse,
    LLMToolCall,
    OpenAICompatibleLocalProvider,
)
from goldenson_api.retrieval.service import WorkspaceRetrievalService
from goldenson_api.schemas.block import BlockCreate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.errors import BadRequestError, NotFoundError
from goldenson_api.services.file_service import FileService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


class FakeProvider:
    def __init__(self, responses: list[LLMResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[Sequence[ChatMessage]] = []
        self.tool_names: list[list[str]] = []

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, object]],
    ) -> LLMResponse:
        self.calls.append(list(messages))
        names: list[str] = []
        for tool in tools:
            function = tool.get("function")
            if isinstance(function, dict) and isinstance(function.get("name"), str):
                names.append(function["name"])
        self.tool_names.append(names)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class RepeatingProvider:
    def __init__(self, tool_name: str, arguments: dict[str, object]) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.count = 0

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, object]],
    ) -> LLMResponse:
        self.count += 1
        return LLMResponse(
            tool_calls=[
                LLMToolCall(
                    id=f"call-{self.count}",
                    name=self.tool_name,
                    arguments=self.arguments,
                )
            ]
        )


class BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, object]],
    ) -> LLMResponse:
        self.started.set()
        await asyncio.Future()
        raise AssertionError("unreachable")


async def seed_workspace(session: AsyncSession, name: str = "Agent Workspace") -> tuple[str, str]:
    workspace = await WorkspaceService(session).create_workspace(WorkspaceCreate(name=name))
    page = await PageService(session).create_page(
        PageCreate(
            workspace_id=workspace.id,
            parent_page_id=None,
            title="Local AI",
            position=0,
        )
    )
    await BlockService(session).create_block(
        BlockCreate(
            page_id=page.id,
            type="paragraph",
            position=0,
            content={"text": "Compare Ollama with llama.cpp for local inference."},
        )
    )
    await session.commit()
    return workspace.id, page.id


async def collect_events(
    service: AgentService, workspace_id: str, message: str
) -> list[dict[str, object]]:
    return [event async for event in service.run(workspace_id, message)]


async def collect_stream_events(
    stream: AsyncIterator[dict[str, object]],
) -> list[dict[str, object]]:
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_retrieval_builds_context_with_real_sources(session: AsyncSession) -> None:
    workspace_id, page_id = await seed_workspace(session)

    result = await WorkspaceRetrievalService(session).search(
        workspace_id, "What am I doing with Ollama local inference?"
    )

    assert "Ollama" in result.context
    assert result.sources
    assert all(source.page_id == page_id for source in result.sources)
    assert all(source.title == "Local AI" for source in result.sources)


@pytest.mark.asyncio
async def test_local_openai_compatible_provider_parses_tool_calls() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "test-local"
        assert payload["think"] is False
        assert payload["reasoning_effort"] == "none"
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "list_pages",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434/v1"
    ) as client:
        provider = OpenAICompatibleLocalProvider(
            "http://127.0.0.1:11434/v1", "test-local", client=client
        )
        response = await provider.complete([ChatMessage(role="user", content="List pages")], [])

    assert response.tool_calls[0].name == "list_pages"
    assert response.tool_calls[0].arguments == {}


@pytest.mark.asyncio
async def test_local_provider_reports_timeout_specifically() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("model stalled", request=request)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11434/v1"
    ) as client:
        provider = OpenAICompatibleLocalProvider(
            "http://127.0.0.1:11434/v1", "test-local", client=client
        )
        with pytest.raises(LLMProviderTimeoutError, match="local model response timed out"):
            await provider.complete([ChatMessage(role="user", content="Hello")], [])


def test_tool_schemas_reject_sql_paths_and_traversal() -> None:
    with pytest.raises(BadRequestError):
        validate_tool_arguments(
            "query_database", {"entity": "pages", "contains": "AI", "sql": "DROP TABLE pages"}
        )
    with pytest.raises(BadRequestError):
        validate_tool_arguments("read_file", {"file_id": "not-a-uuid", "path": "/etc/passwd"})
    with pytest.raises(BadRequestError):
        validate_tool_arguments("create_file", {"name": "../secret", "content": "x"})


@pytest.mark.asyncio
async def test_read_tool_executes_without_approval(session: AsyncSession) -> None:
    workspace_id, page_id = await seed_workspace(session)
    arguments = validate_tool_arguments("get_page", {"page_id": page_id})

    result = await AgentToolExecutor(session, workspace_id).execute("get_page", arguments)

    assert result["page"]["id"] == page_id  # type: ignore[index]
    assert len(result["blocks"]) == 1  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_read_file_rejects_binary_content_declared_as_text(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    file_metadata = await FileService(session).upload_file(
        workspace_id,
        None,
        UploadFile(filename="spoofed.txt", file=io.BytesIO(b"\x00\xffbinary")),
    )
    await session.commit()
    arguments = validate_tool_arguments("read_file", {"file_id": file_metadata.id})

    with pytest.raises(BadRequestError, match="only text workspace files"):
        await AgentToolExecutor(session, workspace_id).execute("read_file", arguments)


@pytest.mark.asyncio
async def test_tool_call_loop_returns_answer_after_read(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(tool_calls=[LLMToolCall(id="read-1", name="list_pages", arguments={})]),
            LLMResponse(content="Your local AI notes compare Ollama and llama.cpp."),
        ]
    )
    service = AgentService(
        session,
        provider,
        max_tool_calls=4,
        max_run_seconds=10,
        tool_timeout_seconds=2,
    )

    events = await collect_events(service, workspace_id, "What am I working on?")

    assert len(provider.calls) == 2
    assert any(event.get("type") == "activity" and "list_pages" in str(event) for event in events)
    assert "Ollama" in "".join(str(event.get("content", "")) for event in events)
    assert events[-1] == {"type": "done", "status": "completed"}


@pytest.mark.asyncio
async def test_simple_question_returns_sources_answer_and_completion(
    session: AsyncSession,
) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider([LLMResponse(content="Your notes compare Ollama with llama.cpp.")])
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "What do my Ollama notes compare?",
    )

    sources = next(event["sources"] for event in events if event.get("type") == "sources")
    assert isinstance(sources, list) and sources
    assert "Ollama with llama.cpp" in "".join(
        str(event.get("content", "")) for event in events if event.get("type") == "text"
    )
    assert len(provider.calls) == 1
    assert "Compare Ollama with llama.cpp for local inference." in provider.calls[0][0].content
    assert events[-1] == {"type": "done", "status": "completed"}


@pytest.mark.asyncio
async def test_question_without_retrieved_evidence_rejects_unsupported_provider_answer(
    session: AsyncSession,
) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider([LLMResponse(content="Your workspace uses Kubernetes in production.")])

    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "How is Kubernetes deployed?",
    )

    sources = next(event["sources"] for event in events if event.get("type") == "sources")
    answer = "".join(
        str(event.get("content", "")) for event in events if event.get("type") == "text"
    )
    assert sources == []
    assert "Kubernetes" not in answer
    assert "couldn't find enough information in your workspace" in answer
    assert events[-1] == {"type": "done", "status": "completed"}


@pytest.mark.asyncio
async def test_empty_read_tool_result_keeps_insufficient_evidence_guard(
    session: AsyncSession,
) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="search-missing",
                        name="search_workspace",
                        arguments={"query": "lunar mining policy", "limit": 6},
                    )
                ]
            ),
            LLMResponse(content="Your workspace requires helium-3 mining permits."),
        ]
    )

    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "What is the lunar mining policy?",
    )

    answer = "".join(
        str(event.get("content", "")) for event in events if event.get("type") == "text"
    )
    assert len(provider.calls) == 2
    assert "helium-3" not in answer
    assert "couldn't find enough information in your workspace" in answer


@pytest.mark.asyncio
async def test_multi_page_question_supplies_bounded_context_matching_emitted_sources(
    session: AsyncSession,
) -> None:
    workspace_id, first_page_id = await seed_workspace(session)
    second_page = await PageService(session).create_page(
        PageCreate(
            workspace_id=workspace_id,
            parent_page_id=None,
            title="Backup policy",
            position=1,
        )
    )
    await BlockService(session).create_block(
        BlockCreate(
            page_id=second_page.id,
            type="paragraph",
            position=0,
            content={"text": "SQLite backups are retained locally for thirty days."},
        )
    )
    await session.commit()
    provider = FakeProvider(
        [
            LLMResponse(
                content="The notes compare local runtimes and retain backups for thirty days."
            )
        ]
    )

    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Summarize Ollama inference and SQLite backup retention.",
    )

    raw_sources = next(event["sources"] for event in events if event.get("type") == "sources")
    assert isinstance(raw_sources, list)
    sources = [source for source in raw_sources if isinstance(source, dict)]
    assert {source.get("page_id") for source in sources} >= {first_page_id, second_page.id}
    assert len(sources) <= 6
    system_prompt = provider.calls[0][0].content
    assert "Synthesize relevant facts across multiple SOURCE blocks" in system_prompt
    assert "what remains unknown" in system_prompt
    assert "plain text without Markdown formatting" in system_prompt
    assert all(str(source["snippet"]) in system_prompt for source in sources)


@pytest.mark.asyncio
async def test_lexical_fallback_still_supplies_grounded_answer_context(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id, _ = await seed_workspace(session)

    async def semantic_unavailable(
        _service: KnowledgeService,
        _workspace_id: str,
        _query: str,
        limit: int = 6,
    ) -> list[tuple[object, float]]:
        return []

    monkeypatch.setattr(KnowledgeService, "semantic_search", semantic_unavailable)
    provider = FakeProvider([LLMResponse(content="The notes compare Ollama with llama.cpp.")])

    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "What do the Ollama inference notes compare?",
    )

    sources = next(event["sources"] for event in events if event.get("type") == "sources")
    assert isinstance(sources, list) and sources
    assert any(
        isinstance(source, dict) and source.get("block_id") is not None for source in sources
    )
    assert "Compare Ollama with llama.cpp" in provider.calls[0][0].content


@pytest.mark.asyncio
async def test_write_requires_approval_then_executes(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(content="Created Agent Draft and verified the change."),
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )

    events = await collect_events(service, workspace_id, "Create a page called Agent Draft")
    pages_before = await PageService(session).list_pages(workspace_id)
    proposal_event = next(event for event in events if event.get("type") == "proposal")
    proposal = proposal_event["proposal"]
    assert isinstance(proposal, dict)
    assert [page.title for page in pages_before] == ["Local AI"]

    resumed = [
        event async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
    ]
    pages_after = await PageService(session).list_pages(workspace_id)

    assert any("Approved" in str(event.get("message")) for event in resumed)
    assert any(
        event.get("type") == "workspace_changed" and event.get("tool_name") == "create_page"
        for event in resumed
    )
    assert "verified" in "".join(str(event.get("content", "")) for event in resumed)
    assert resumed[-1] == {"type": "done", "status": "completed"}
    assert [page.title for page in pages_after] == ["Local AI", "Agent Draft"]
    assert len(provider.calls) == 1
    assert provider.calls[0][-1].role == "tool"


@pytest.mark.asyncio
async def test_simple_create_page_reaches_approval_without_irrelevant_retrieval(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_id, _ = await seed_workspace(session)

    async def unexpected_retrieval(
        _service: WorkspaceRetrievalService,
        _workspace_id: str,
        _query: str,
        _limit: int = 6,
    ) -> object:
        raise AssertionError("self-contained create_page should not scan workspace content")

    monkeypatch.setattr(WorkspaceRetrievalService, "search", unexpected_retrieval)
    lifecycle_logs: list[str] = []

    def capture_lifecycle_log(message: str, *arguments: object) -> None:
        lifecycle_logs.append(message % arguments)

    monkeypatch.setattr("goldenson_api.agent.service.logger.debug", capture_lifecycle_log)
    provider = FakeProvider([])

    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Create a page called Test Agent",
    )

    proposal = next(event["proposal"] for event in events if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    assert proposal["tool_name"] == "create_page"
    assert proposal["arguments"] == {
        "title": "Test Agent",
        "parent_page_id": None,
        "position": 1,
    }
    assert provider.calls == []
    lifecycle_log = "\n".join(lifecycle_logs)
    assert "stage=retrieval" in lifecycle_log
    assert "skipped=True" in lifecycle_log
    assert "stage=provider" in lifecycle_log
    assert "stage=approval_ready" in lifecycle_log


@pytest.mark.asyncio
async def test_rejected_write_is_not_executed(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="write-2",
                        name="create_page",
                        arguments={"title": "Rejected Draft", "position": 1},
                    )
                ]
            ),
            LLMResponse(content="I left the workspace unchanged."),
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    events = await collect_events(service, workspace_id, "Create a page")
    proposal = next(event["proposal"] for event in events if event.get("type") == "proposal")
    assert isinstance(proposal, dict)

    resumed = [
        event async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), False)
    ]

    assert any("Rejected" in str(event.get("message")) for event in resumed)
    assert "unchanged" in "".join(str(event.get("content", "")) for event in resumed)
    assert resumed[-1] == {"type": "done", "status": "completed"}
    assert [page.title for page in await PageService(session).list_pages(workspace_id)] == [
        "Local AI"
    ]
    assert '"status": "rejected"' in provider.calls[1][-1].content
    with pytest.raises(BadRequestError, match="already decided differently"):
        _ = [
            event
            async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
        ]


@pytest.mark.asyncio
async def test_delete_requires_approval_and_rejection_preserves_page(session: AsyncSession) -> None:
    workspace_id, page_id = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="delete-1",
                        name="delete_page",
                        arguments={"page_id": page_id},
                    )
                ]
            ),
            LLMResponse(content="The page was preserved."),
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    events = await collect_events(service, workspace_id, "Delete Local AI")
    proposal = next(event["proposal"] for event in events if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    assert proposal["permission"] == "DESTRUCTIVE"
    assert await PageService(session).get_page(page_id) is not None

    _ = [
        event async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), False)
    ]
    assert await PageService(session).get_page(page_id) is not None


@pytest.mark.asyncio
async def test_read_write_approve_read_verify_then_final_answer(
    session: AsyncSession,
) -> None:
    workspace_id, page_id = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(tool_calls=[LLMToolCall(id="read-1", name="list_pages", arguments={})]),
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="write-1",
                        name="create_task",
                        arguments={
                            "page_id": page_id,
                            "text": "Verify local inference",
                            "position": 1,
                        },
                    )
                ]
            ),
            LLMResponse(
                tool_calls=[
                    LLMToolCall(id="verify-1", name="get_page", arguments={"page_id": page_id})
                ]
            ),
            LLMResponse(content="The task was created and verified."),
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=5, max_run_seconds=10, tool_timeout_seconds=2
    )

    initial = await collect_events(service, workspace_id, "Create and verify a task")
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    assert initial[-1] == {"type": "done", "status": "waiting_for_approval"}

    resumed = [
        event async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
    ]

    assert len(provider.calls) == 4
    assert any(event.get("type") == "activity" and "get_page" in str(event) for event in resumed)
    assert "created and verified" in "".join(str(event.get("content", "")) for event in resumed)
    assert resumed[-1] == {"type": "done", "status": "completed"}
    run_id = str(initial[0]["run_id"])
    run = await AgentAuditRepository(session).get_run(run_id)
    assert run is not None
    assert run.tool_call_count == 3
    assert run.status == "completed"


@pytest.mark.asyncio
async def test_approved_tool_database_failure_is_audited(session: AsyncSession) -> None:
    workspace_id, page_id = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="conflicting-task",
                        name="create_task",
                        arguments={
                            "page_id": page_id,
                            "text": "Conflicting task",
                            "position": 0,
                        },
                    )
                ]
            )
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    initial = await collect_events(service, workspace_id, "Create a conflicting task")
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)

    resumed = [
        event async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
    ]

    assert resumed[-1] == {"type": "done", "status": "failed"}
    tool_call = await AgentAuditRepository(session).get_tool_call(str(proposal["tool_call_id"]))
    assert tool_call is not None
    assert tool_call.error_summary == "tool execution failed"
    run = await AgentAuditRepository(session).get_run(tool_call.run_id)
    assert run is not None
    assert run.status == "failed"


@pytest.mark.asyncio
async def test_duplicate_and_conflicting_approval_do_not_execute_twice(
    session: AsyncSession,
) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="write-once",
                        name="create_page",
                        arguments={"title": "Only Once", "position": 1},
                    )
                ]
            ),
            LLMResponse(content="Done."),
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    initial = await collect_events(service, workspace_id, "Create one page")
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    tool_call_id = str(proposal["tool_call_id"])

    first = [event async for event in service.decide(workspace_id, tool_call_id, True)]
    duplicate = [event async for event in service.decide(workspace_id, tool_call_id, True)]
    reconnected = [
        event async for event in service.reconnect(workspace_id, str(initial[0]["run_id"]))
    ]

    assert first[-1] == {"type": "done", "status": "completed"}
    assert duplicate[-1] == {"type": "done", "status": "completed"}
    assert reconnected[-1] == {"type": "done", "status": "completed"}
    assert sum(event.get("type") == "workspace_changed" for event in first) == 1
    assert not any(event.get("type") == "workspace_changed" for event in duplicate)
    assert not any(event.get("type") == "workspace_changed" for event in reconnected)
    assert [page.title for page in await PageService(session).list_pages(workspace_id)].count(
        "Only Once"
    ) == 1
    with pytest.raises(BadRequestError, match="already decided differently"):
        _ = [event async for event in service.decide(workspace_id, tool_call_id, False)]


@pytest.mark.asyncio
async def test_concurrent_approval_claim_has_exactly_one_winner(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as setup_session:
        workspace_id, _ = await seed_workspace(setup_session)
        provider = FakeProvider(
            [
                LLMResponse(
                    tool_calls=[
                        LLMToolCall(
                            id="race-write",
                            name="create_page",
                            arguments={"title": "Claimed Once", "position": 1},
                        )
                    ]
                )
            ]
        )
        initial = await collect_events(
            AgentService(
                setup_session,
                provider,
                max_tool_calls=4,
                max_run_seconds=10,
                tool_timeout_seconds=2,
            ),
            workspace_id,
            "Create a page",
        )
        proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
        assert isinstance(proposal, dict)
        tool_call_id = str(proposal["tool_call_id"])

    async def claim() -> bool:
        async with session_factory() as claim_session:
            claimed = await AgentAuditRepository(claim_session).claim_tool_call_decision(
                tool_call_id, "approved"
            )
            await claim_session.commit()
            return claimed

    claims = await asyncio.gather(claim(), claim())
    assert sorted(claims) == [False, True]


@pytest.mark.asyncio
async def test_stale_arguments_are_revalidated_before_approval(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="stale-write",
                        name="create_page",
                        arguments={"title": "Unsafe", "position": 1},
                    )
                ]
            )
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    initial = await collect_events(service, workspace_id, "Create a page")
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    tool_call = await AgentAuditRepository(session).get_tool_call(str(proposal["tool_call_id"]))
    assert tool_call is not None
    tool_call.arguments = {**tool_call.arguments, "sql": "DROP TABLE pages"}
    await session.commit()

    with pytest.raises(BadRequestError, match="invalid agent tool arguments"):
        _ = [
            event
            async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
        ]
    assert [page.title for page in await PageService(session).list_pages(workspace_id)] == [
        "Local AI"
    ]


@pytest.mark.asyncio
async def test_waiting_run_can_be_cancelled_and_cannot_resume(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="cancel-write",
                        name="create_page",
                        arguments={"title": "Cancelled", "position": 1},
                    )
                ]
            )
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    initial = await collect_events(service, workspace_id, "Create a page")
    run_id = str(initial[0]["run_id"])
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)

    assert await cancel_persisted_agent_run(session, run_id)
    with pytest.raises(BadRequestError, match="not waiting"):
        _ = [
            event
            async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
        ]
    reconnected = [event async for event in service.reconnect(workspace_id, run_id)]
    assert reconnected[-1] == {"type": "done", "status": "cancelled"}


@pytest.mark.asyncio
async def test_expired_waiting_run_times_out_without_execution(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="late-write",
                        name="create_page",
                        arguments={"title": "Too Late", "position": 1},
                    )
                ]
            )
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    initial = await collect_events(service, workspace_id, "Create a page")
    run_id = str(initial[0]["run_id"])
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    run = await AgentAuditRepository(session).get_run(run_id)
    assert run is not None
    run.remaining_seconds = 0
    await session.commit()

    events = [
        event async for event in service.decide(workspace_id, str(proposal["tool_call_id"]), True)
    ]
    assert events[-1] == {"type": "done", "status": "timed_out"}
    assert [page.title for page in await PageService(session).list_pages(workspace_id)] == [
        "Local AI"
    ]


@pytest.mark.asyncio
async def test_approval_enforces_workspace_isolation(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    other_workspace_id, _ = await seed_workspace(session, "Other Workspace")
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="isolated-write",
                        name="create_page",
                        arguments={"title": "Private", "position": 1},
                    )
                ]
            )
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    initial = await collect_events(service, workspace_id, "Create a page")
    proposal = next(event["proposal"] for event in initial if event.get("type") == "proposal")
    assert isinstance(proposal, dict)

    with pytest.raises(NotFoundError):
        _ = [
            event
            async for event in service.decide(
                other_workspace_id, str(proposal["tool_call_id"]), True
            )
        ]


@pytest.mark.asyncio
async def test_circuit_breaker_stops_unbounded_tool_loop(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = RepeatingProvider("list_pages", {})
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=1, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Keep listing",
    )

    assert provider.count == 2
    assert any(event.get("type") == "done" and event.get("status") == "failed" for event in events)
    assert any("maximum tool calls" in str(event.get("message")) for event in events)


@pytest.mark.asyncio
async def test_provider_failure_emits_safe_error(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider([httpx.ConnectError("local server unavailable")])
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Question",
    )

    assert any(event.get("type") == "error" for event in events)
    assert all("ConnectError" not in str(event) for event in events)
    assert events[-1] == {"type": "done", "status": "failed"}


@pytest.mark.asyncio
async def test_provider_timeout_emits_specific_error(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider([LLMProviderTimeoutError("local model response timed out")])
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Question",
    )

    assert any("local model took too long" in str(event.get("message")) for event in events)
    assert all("maximum run duration" not in str(event) for event in events)
    assert events[-1] == {"type": "done", "status": "timed_out"}


@pytest.mark.asyncio
async def test_cancellation_interrupts_in_flight_provider(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = BlockingProvider()
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    stream = service.run(workspace_id, "Long question")
    run_event = await anext(stream)
    remaining = asyncio.create_task(collect_stream_events(stream))
    await provider.started.wait()

    assert cancel_agent_run(str(run_event["run_id"]))
    events = await asyncio.wait_for(remaining, timeout=1)

    assert events[-1] == {"type": "done", "status": "cancelled"}


@pytest.mark.asyncio
async def test_client_disconnect_preserves_resumable_run(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = BlockingProvider()
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )
    stream = service.run(workspace_id, "Long question")
    run_event = await anext(stream)

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(collect_stream_events, stream)
        await provider.started.wait()
        task_group.cancel_scope.cancel()

    run = await AgentAuditRepository(session).get_run(str(run_event["run_id"]))
    assert run is not None
    assert run.status == "resuming"


@pytest.mark.asyncio
async def test_agent_redacts_secrets_before_provider_call(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider([LLMResponse(content="Done")])

    events = await collect_events(
        AgentService(
            session,
            provider,
            max_tool_calls=4,
            max_run_seconds=10,
            tool_timeout_seconds=2,
        ),
        workspace_id,
        "Summarize this token=super-secret-value",
    )

    provider_messages = provider.calls[0]
    assert "super-secret-value" not in provider_messages[1].content
    assert "token=[REDACTED]" in provider_messages[1].content
    run = await AgentAuditRepository(session).get_run(str(events[0]["run_id"]))
    assert run is not None
    assert "super-secret-value" not in json.dumps(run.messages)


@pytest.mark.asyncio
async def test_pending_tool_arguments_are_sanitized_in_audit(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="secret-write",
                        name="create_file",
                        arguments={"name": "notes.txt", "content": "token=private-value"},
                    )
                ]
            )
        ]
    )
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Create a private note",
    )
    proposal = next(event["proposal"] for event in events if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    tool_call = await AgentAuditRepository(session).get_tool_call(str(proposal["tool_call_id"]))
    assert tool_call is not None
    assert "private-value" not in json.dumps(tool_call.arguments)
    assert "[REDACTED]" in json.dumps(tool_call.arguments)
    assert tool_call.execution_arguments == {
        "name": "notes.txt",
        "content": "token=private-value",
        "page_id": None,
    }


def test_agent_sse_streams_text_sources_and_completion(api_client: TestClient) -> None:
    workspace = api_client.post("/api/workspaces", json={"name": "SSE Workspace"}).json()
    page = api_client.post(
        f"/api/workspaces/{workspace['id']}/pages",
        json={"title": "Ollama Notes", "parent_page_id": None, "position": 0},
    ).json()
    api_client.post(
        f"/api/pages/{page['id']}/blocks",
        json={"type": "paragraph", "position": 0, "content": {"text": "Ollama runs locally."}},
    )
    provider = FakeProvider([LLMResponse(content="Ollama appears in your local notes.")])
    app = cast(FastAPI, api_client.app)
    app.dependency_overrides[get_llm_provider] = lambda: provider

    response = api_client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs",
        json={"message": "What are my Ollama notes?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: sources" in response.text
    assert page["id"] in response.text
    assert "event: text" in response.text
    assert "event: done" in response.text


def test_agent_approval_sse_resumes_same_run_to_completion(api_client: TestClient) -> None:
    workspace = api_client.post("/api/workspaces", json={"name": "Approval SSE"}).json()
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="api-write",
                        name="create_page",
                        arguments={"title": "Approved Page", "position": 0},
                    )
                ]
            ),
            LLMResponse(content="The page was created and verified."),
        ]
    )
    app = cast(FastAPI, api_client.app)
    app.dependency_overrides[get_llm_provider] = lambda: provider
    initial = api_client.post(
        f"/api/workspaces/{workspace['id']}/agent/runs",
        json={"message": "Create an approved page"},
    )
    proposal_data = next(
        json.loads(line.removeprefix("data: "))
        for line in initial.text.splitlines()
        if line.startswith("data: ") and '"type":"proposal"' in line
    )
    tool_call_id = proposal_data["proposal"]["tool_call_id"]

    resumed = api_client.post(
        f"/api/workspaces/{workspace['id']}/agent/tool-calls/{tool_call_id}/decision",
        json={"approved": True},
    )

    assert resumed.status_code == 200
    assert resumed.headers["content-type"].startswith("text/event-stream")
    assert '"message":"Approved \\u2014 continuing..."' in resumed.text
    assert "created and verified" in resumed.text
    assert '"status":"completed"' in resumed.text
    pages = api_client.get(f"/api/workspaces/{workspace['id']}/pages").json()["items"]
    assert [page["title"] for page in pages] == ["Approved Page"]
