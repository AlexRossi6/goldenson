from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.agent.schemas import AgentRunRequest, ApprovalDecision
from goldenson_api.agent.service import AgentService, cancel_persisted_agent_run
from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.local_ai import Runtime
from goldenson_api.core.config import get_settings
from goldenson_api.inference.provider import LLMProvider, OpenAICompatibleLocalProvider
from goldenson_api.local_ai.service import LocalAIService
from goldenson_api.services.errors import NotFoundError

router = APIRouter(tags=["Agent"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_llm_provider(
    session: DbSession,
    runtime: Runtime,
) -> LLMProvider:
    settings = get_settings()
    model = await LocalAIService(session, runtime, settings.storage_root).selected_ready_model()
    return OpenAICompatibleLocalProvider(
        f"{settings.ollama_base_url}/v1",
        model,
        timeout_seconds=settings.agent_provider_timeout_seconds,
    )


LLM = Annotated[LLMProvider, Depends(get_llm_provider)]


def _sse(event: dict[str, object]) -> str:
    event_type = str(event.get("type", "message"))
    return f"event: {event_type}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


def _agent_service(session: AsyncSession, provider: LLMProvider) -> AgentService:
    settings = get_settings()
    return AgentService(
        session,
        provider,
        max_tool_calls=settings.agent_max_tool_calls,
        max_run_seconds=settings.agent_max_run_seconds,
        tool_timeout_seconds=settings.agent_tool_timeout_seconds,
    )


@router.post(
    "/workspaces/{workspace_id}/agent/runs",
    summary="Run the local workspace agent",
)
async def run_agent(
    workspace_id: UUID,
    payload: AgentRunRequest,
    session: DbSession,
    provider: LLM,
) -> StreamingResponse:
    service = _agent_service(session, provider)

    async def events() -> AsyncIterator[str]:
        async for event in service.run(str(workspace_id), payload.message):
            yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/workspaces/{workspace_id}/agent/tool-calls/{tool_call_id}/decision",
    summary="Approve or reject an agent change",
)
async def decide_agent_tool_call(
    workspace_id: UUID,
    tool_call_id: UUID,
    payload: ApprovalDecision,
    session: DbSession,
    provider: LLM,
) -> StreamingResponse:
    service = _agent_service(session, provider)

    async def events() -> AsyncIterator[str]:
        async for event in service.decide(str(workspace_id), str(tool_call_id), payload.approved):
            yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/workspaces/{workspace_id}/agent/runs/{run_id}/events",
    summary="Reconnect to a persisted agent run",
)
async def reconnect_agent_run(
    workspace_id: UUID,
    run_id: UUID,
    session: DbSession,
    provider: LLM,
) -> StreamingResponse:
    service = _agent_service(session, provider)

    async def events() -> AsyncIterator[str]:
        async for event in service.reconnect(str(workspace_id), str(run_id)):
            yield _sse(event)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/workspaces/{workspace_id}/agent/runs/{run_id}/cancel",
    summary="Cancel a running agent request",
)
async def cancel_run(workspace_id: UUID, run_id: UUID, session: DbSession) -> dict[str, object]:
    if not await cancel_persisted_agent_run(session, str(run_id), str(workspace_id)):
        raise NotFoundError("running agent request not found")
    return {"status": "cancelling", "run_id": str(run_id)}
