from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.agent.service import (
    AgentService,
    ApprovalService,
    cancel_agent_run,
)
from goldenson_api.agent.tools import AgentToolExecutor, validate_tool_arguments
from goldenson_api.api.agent import get_llm_provider
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
from goldenson_api.services.errors import BadRequestError
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


class FakeProvider:
    def __init__(self, responses: list[LLMResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[Sequence[ChatMessage]] = []

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        tools: Sequence[dict[str, object]],
    ) -> LLMResponse:
        self.calls.append(messages)
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
    provider = FakeProvider([LLMResponse(content="This workspace compares local AI runtimes.")])
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "What is this workspace about?",
    )

    sources = next(event["sources"] for event in events if event.get("type") == "sources")
    assert isinstance(sources, list)
    assert "local AI runtimes" in "".join(
        str(event.get("content", "")) for event in events if event.get("type") == "text"
    )
    assert len(provider.calls) == 1
    assert events[-1] == {"type": "done", "status": "completed"}


@pytest.mark.asyncio
async def test_write_requires_approval_then_executes(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider(
        [
            LLMResponse(
                tool_calls=[
                    LLMToolCall(
                        id="write-1",
                        name="create_page",
                        arguments={"title": "Agent Draft", "position": 1},
                    )
                ]
            )
        ]
    )
    service = AgentService(
        session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
    )

    events = await collect_events(service, workspace_id, "Create an Agent Draft page")
    pages_before = await PageService(session).list_pages(workspace_id)
    proposal_event = next(event for event in events if event.get("type") == "proposal")
    proposal = proposal_event["proposal"]
    assert isinstance(proposal, dict)
    assert [page.title for page in pages_before] == ["Local AI"]

    result = await ApprovalService(session, 2).decide(
        workspace_id, str(proposal["tool_call_id"]), True
    )
    pages_after = await PageService(session).list_pages(workspace_id)

    assert result["status"] == "completed"
    assert [page.title for page in pages_after] == ["Local AI", "Agent Draft"]


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
            )
        ]
    )
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Create a page",
    )
    proposal = next(event["proposal"] for event in events if event.get("type") == "proposal")
    assert isinstance(proposal, dict)

    result = await ApprovalService(session, 2).decide(
        workspace_id, str(proposal["tool_call_id"]), False
    )

    assert result["status"] == "rejected"
    assert [page.title for page in await PageService(session).list_pages(workspace_id)] == [
        "Local AI"
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
            )
        ]
    )
    events = await collect_events(
        AgentService(
            session, provider, max_tool_calls=4, max_run_seconds=10, tool_timeout_seconds=2
        ),
        workspace_id,
        "Delete Local AI",
    )
    proposal = next(event["proposal"] for event in events if event.get("type") == "proposal")
    assert isinstance(proposal, dict)
    assert proposal["permission"] == "DESTRUCTIVE"
    assert await PageService(session).get_page(page_id) is not None

    await ApprovalService(session, 2).decide(workspace_id, str(proposal["tool_call_id"]), False)
    assert await PageService(session).get_page(page_id) is not None


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
    assert any(event.get("type") == "done" and event.get("status") == "stopped" for event in events)
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
    assert events[-1] == {"type": "done", "status": "error"}


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
    assert events[-1] == {"type": "done", "status": "error"}


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
async def test_agent_redacts_secrets_before_provider_call(session: AsyncSession) -> None:
    workspace_id, _ = await seed_workspace(session)
    provider = FakeProvider([LLMResponse(content="Done")])

    await collect_events(
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
