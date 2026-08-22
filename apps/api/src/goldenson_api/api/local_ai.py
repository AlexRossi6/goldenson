from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.core.config import get_settings
from goldenson_api.local_ai.installer import MacOSOllamaInstaller, OllamaInstaller
from goldenson_api.local_ai.runtime import OllamaHTTPRuntime, OllamaRuntime
from goldenson_api.local_ai.schemas import (
    LocalAIStatus,
    ModelActionResponse,
    RuntimeStatus,
    SelectModelRequest,
)
from goldenson_api.local_ai.service import LocalAIService
from goldenson_api.services.errors import BadRequestError

router = APIRouter(prefix="/local-ai", tags=["Local AI"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


def get_ollama_runtime() -> OllamaRuntime:
    settings = get_settings()
    return OllamaHTTPRuntime(
        settings.ollama_base_url,
        runtime_root=settings.ollama_runtime_root,
        timeout_seconds=settings.agent_tool_timeout_seconds,
    )


Runtime = Annotated[OllamaRuntime, Depends(get_ollama_runtime)]


def get_ollama_installer() -> OllamaInstaller:
    if sys.platform != "darwin":
        raise BadRequestError("automatic Ollama installation currently supports macOS only")
    return MacOSOllamaInstaller(get_settings().ollama_runtime_root)


Installer = Annotated[OllamaInstaller, Depends(get_ollama_installer)]


def _service(session: AsyncSession, runtime: OllamaRuntime) -> LocalAIService:
    return LocalAIService(session, runtime, get_settings().storage_root)


def _sse(event: dict[str, object]) -> str:
    event_type = str(event.get("state", "progress"))
    return f"event: {event_type}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"


@router.get("/status", response_model=LocalAIStatus, summary="Get local AI status")
async def get_local_ai_status(session: DbSession, runtime: Runtime) -> LocalAIStatus:
    return await _service(session, runtime).get_status()


@router.post(
    "/runtime/start", response_model=RuntimeStatus, summary="Start the local Ollama runtime"
)
async def start_local_runtime(session: DbSession, runtime: Runtime) -> RuntimeStatus:
    return await _service(session, runtime).start_runtime()


@router.post("/runtime/install", summary="Install the local Ollama runtime")
async def install_local_runtime(installer: Installer) -> StreamingResponse:
    async def events() -> AsyncIterator[str]:
        async for event in installer.install():
            yield _sse(event.model_dump(mode="json"))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/models/select", response_model=LocalAIStatus, summary="Select a local model")
async def select_local_model(
    payload: SelectModelRequest,
    session: DbSession,
    runtime: Runtime,
) -> LocalAIStatus:
    return await _service(session, runtime).select_model(payload.model_id)


@router.post("/models/{model_id}/install", summary="Install an allowlisted local model")
async def install_local_model(
    model_id: str,
    session: DbSession,
    runtime: Runtime,
) -> StreamingResponse:
    service = _service(session, runtime)

    async def events() -> AsyncIterator[str]:
        async for event in service.install_model(model_id):
            yield _sse(event.model_dump(mode="json"))

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/models/{model_id}/cancel",
    response_model=ModelActionResponse,
    summary="Cancel a model installation",
)
async def cancel_model_installation(
    model_id: str,
    session: DbSession,
    runtime: Runtime,
) -> ModelActionResponse:
    if not _service(session, runtime).cancel_installation(model_id):
        raise BadRequestError("model installation is not running")
    return ModelActionResponse(status="cancelling", model_id=model_id)


@router.delete(
    "/models/{model_id}",
    response_model=LocalAIStatus,
    summary="Remove an installed local model",
)
async def remove_local_model(
    model_id: str,
    session: DbSession,
    runtime: Runtime,
) -> LocalAIStatus:
    return await _service(session, runtime).remove_model(model_id)
