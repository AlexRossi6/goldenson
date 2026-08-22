from __future__ import annotations

import asyncio
import plistlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.agent import get_llm_provider
from goldenson_api.api.local_ai import get_ollama_installer, get_ollama_runtime
from goldenson_api.local_ai.installer import MAX_DOWNLOAD_BYTES, MacOSOllamaInstaller
from goldenson_api.local_ai.runtime import InstalledModel, OllamaHTTPRuntime, PullProgress
from goldenson_api.local_ai.schemas import (
    InstallationState,
    RuntimeInstallationState,
    RuntimeInstallProgressEvent,
)
from goldenson_api.local_ai.service import LocalAIService, _installation_jobs
from goldenson_api.services.errors import BadRequestError

GIB = 1024**3


class FakeOllamaRuntime:
    def __init__(
        self,
        *,
        reachable: bool = True,
        binary: bool = True,
        models: list[InstalledModel] | None = None,
        pull_error: str | None = None,
    ) -> None:
        self.reachable = reachable
        self.binary = binary
        self.models = list(models or [])
        self.pull_error = pull_error
        self.pull_count = 0
        self.removed: list[str] = []
        self.pull_gate: asyncio.Event | None = None

    def binary_path(self) -> str | None:
        return "/usr/local/bin/ollama" if self.binary else None

    async def version(self) -> str:
        if not self.reachable:
            raise RuntimeError("connection refused")
        return "0.11.0"

    async def list_models(self) -> list[InstalledModel]:
        if not self.reachable:
            raise RuntimeError("connection refused")
        return list(self.models)

    async def pull_model(self, model_id: str) -> AsyncIterator[PullProgress]:
        self.pull_count += 1
        if self.pull_error:
            raise RuntimeError(self.pull_error)
        yield PullProgress(status="downloading", completed=50, total=100)
        if self.pull_gate is not None:
            await self.pull_gate.wait()
        self.models.append(InstalledModel(name=model_id, size=100))
        yield PullProgress(status="success", completed=100, total=100)

    async def remove_model(self, model_id: str) -> None:
        self.removed.append(model_id)
        self.models = [model for model in self.models if model.name != model_id]

    async def start(self) -> bool:
        if not self.binary:
            return False
        self.reachable = True
        return True


class FakeOllamaInstaller:
    async def install(self) -> AsyncIterator[RuntimeInstallProgressEvent]:
        yield RuntimeInstallProgressEvent(
            state=RuntimeInstallationState.DOWNLOADING,
            progress=0.5,
            downloaded_bytes=50,
            total_bytes=100,
            message="Downloading Ollama...",
        )
        yield RuntimeInstallProgressEvent(
            state=RuntimeInstallationState.READY,
            progress=1,
            downloaded_bytes=100,
            total_bytes=100,
            message="Ollama is installed and ready to start.",
        )


@pytest.fixture(autouse=True)
def clear_installation_jobs() -> None:
    _installation_jobs.clear()


def service(
    session: AsyncSession,
    runtime: FakeOllamaRuntime,
    *,
    disk_free: int = 100 * GIB,
    memory: int = 16 * GIB,
) -> LocalAIService:
    return LocalAIService(
        session,
        runtime,
        Path("/unused"),
        disk_free=lambda _path: disk_free,
        total_memory=lambda: memory,
    )


@pytest.mark.asyncio
async def test_ollama_unavailable_has_meaningful_runtime_state(session: AsyncSession) -> None:
    status = await service(session, FakeOllamaRuntime(reachable=False)).get_status()

    assert status.runtime.installed is True
    assert status.runtime.reachable is False
    assert status.runtime.usable is False
    assert status.runtime.error == "Ollama is installed but not running."
    assert all(model.state == InstallationState.AVAILABLE for model in status.models)


@pytest.mark.asyncio
async def test_ollama_available_without_models_needs_setup(session: AsyncSession) -> None:
    status = await service(session, FakeOllamaRuntime()).get_status()

    assert status.runtime.reachable is True
    assert status.runtime.version == "0.11.0"
    assert status.selected_model is None


@pytest.mark.asyncio
async def test_installed_model_is_detected_and_automatically_selected(
    session: AsyncSession,
) -> None:
    runtime = FakeOllamaRuntime(models=[InstalledModel(name="qwen3:8b", size=5 * GIB)])

    status = await service(session, runtime).get_status()

    selected = next(model for model in status.models if model.id == "qwen3:8b")
    assert status.selected_model == "qwen3:8b"
    assert selected.state == InstallationState.READY
    assert selected.installed_size_bytes == 5 * GIB
    assert selected.selected is True


@pytest.mark.asyncio
async def test_missing_model_remains_available(session: AsyncSession) -> None:
    status = await service(session, FakeOllamaRuntime()).get_status()

    model = next(model for model in status.models if model.id == "qwen3:8b")
    assert model.state == InstallationState.AVAILABLE
    assert model.selected is False


@pytest.mark.asyncio
async def test_install_skips_model_already_installed(session: AsyncSession) -> None:
    runtime = FakeOllamaRuntime(models=[InstalledModel(name="qwen3:8b", size=100)])

    events = [event async for event in service(session, runtime).install_model("qwen3:8b")]

    assert events[-1].state == InstallationState.READY
    assert runtime.pull_count == 0


@pytest.mark.asyncio
async def test_model_installation_success_reports_progress(session: AsyncSession) -> None:
    runtime = FakeOllamaRuntime()

    events = [event async for event in service(session, runtime).install_model("qwen3:8b")]

    assert [event.state for event in events] == [
        InstallationState.CHECKING,
        InstallationState.DOWNLOADING,
        InstallationState.DOWNLOADING,
        InstallationState.INSTALLING,
        InstallationState.READY,
    ]
    assert events[2].progress == 0.5
    assert events[-1].progress == 1


@pytest.mark.asyncio
async def test_model_installation_failure_is_terminal_and_retryable(
    session: AsyncSession,
) -> None:
    runtime = FakeOllamaRuntime(pull_error="download failed")
    local_ai = service(session, runtime)

    first_events = [event async for event in local_ai.install_model("qwen3:8b")]
    runtime.pull_error = None
    retry_events = [event async for event in local_ai.install_model("qwen3:8b")]

    assert first_events[-1].state == InstallationState.FAILED
    assert first_events[-1].message == "download failed"
    assert retry_events[-1].state == InstallationState.READY


@pytest.mark.asyncio
async def test_model_installation_can_be_cancelled(session: AsyncSession) -> None:
    runtime = FakeOllamaRuntime()
    runtime.pull_gate = asyncio.Event()
    local_ai = service(session, runtime)
    stream = local_ai.install_model("qwen3:8b")

    assert (await anext(stream)).state == InstallationState.CHECKING
    assert (await anext(stream)).state == InstallationState.DOWNLOADING
    assert (await anext(stream)).state == InstallationState.DOWNLOADING
    assert local_ai.cancel_installation("qwen3:8b") is True
    runtime.pull_gate.set()

    cancelled = await anext(stream)
    assert cancelled.state == InstallationState.CANCELLED


@pytest.mark.asyncio
async def test_model_selection_and_invalid_selection(session: AsyncSession) -> None:
    runtime = FakeOllamaRuntime(models=[InstalledModel(name="gemma3:4b", size=100)])
    local_ai = service(session, runtime)

    status = await local_ai.select_model("gemma3:4b")

    assert status.selected_model == "gemma3:4b"
    with pytest.raises(BadRequestError, match="not installed"):
        await local_ai.select_model("qwen3:8b")
    with pytest.raises(BadRequestError, match="supported catalog"):
        await local_ai.select_model("arbitrary/model:url")


@pytest.mark.asyncio
async def test_selected_model_must_change_before_removal(session: AsyncSession) -> None:
    runtime = FakeOllamaRuntime(
        models=[
            InstalledModel(name="gemma3:4b", size=100),
            InstalledModel(name="llama3.2:3b", size=100),
        ]
    )
    local_ai = service(session, runtime)
    await local_ai.select_model("gemma3:4b")

    with pytest.raises(BadRequestError, match="select another model"):
        await local_ai.remove_model("gemma3:4b")

    await local_ai.select_model("llama3.2:3b")
    status = await local_ai.remove_model("gemma3:4b")
    assert runtime.removed == ["gemma3:4b"]
    assert next(model for model in status.models if model.id == "gemma3:4b").state == "available"


@pytest.mark.asyncio
async def test_provider_has_no_fallback_when_no_model_is_ready(session: AsyncSession) -> None:
    runtime = FakeOllamaRuntime(reachable=False)

    with pytest.raises(BadRequestError, match="no local AI model is ready"):
        await get_llm_provider(session, runtime)


def test_installation_progress_streams_over_sse(api_client: TestClient) -> None:
    runtime = FakeOllamaRuntime()
    app = cast(FastAPI, api_client.app)
    app.dependency_overrides[get_ollama_runtime] = lambda: runtime

    response = api_client.post("/api/local-ai/models/qwen3%3A8b/install")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"state":"downloading"' in response.text
    assert '"progress":0.5' in response.text
    assert '"state":"ready"' in response.text


def test_runtime_installation_progress_streams_over_sse(api_client: TestClient) -> None:
    app = cast(FastAPI, api_client.app)
    app.dependency_overrides[get_ollama_installer] = FakeOllamaInstaller

    response = api_client.post("/api/local-ai/runtime/install")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"state":"downloading"' in response.text
    assert '"progress":0.5' in response.text
    assert '"state":"ready"' in response.text


def test_runtime_installer_rejects_unexpected_bundle_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "Ollama.app"
    resources = application / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "ollama").write_bytes(b"binary")
    with (application / "Contents" / "Info.plist").open("wb") as info_file:
        plistlib.dump({"CFBundleIdentifier": "invalid.bundle"}, info_file)
    monkeypatch.setattr(MacOSOllamaInstaller, "_run", lambda *_args: "")

    with pytest.raises(RuntimeError, match="bundle identifier"):
        MacOSOllamaInstaller._verify(application)


def test_runtime_installer_rejects_unexpected_signing_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = tmp_path / "Ollama.app"
    resources = application / "Contents" / "Resources"
    resources.mkdir(parents=True)
    (resources / "ollama").write_bytes(b"binary")
    with (application / "Contents" / "Info.plist").open("wb") as info_file:
        plistlib.dump({"CFBundleIdentifier": "com.electron.ollama"}, info_file)
    monkeypatch.setattr(
        MacOSOllamaInstaller,
        "_run",
        lambda *_args: "TeamIdentifier=WRONGTEAM",
    )

    with pytest.raises(RuntimeError, match="expected developer"):
        MacOSOllamaInstaller._verify(application)


def test_runtime_installer_rejects_oversized_download() -> None:
    response = httpx.Response(
        200,
        headers={"content-length": str(MAX_DOWNLOAD_BYTES + 1)},
    )

    with pytest.raises(RuntimeError, match="outside the allowed range"):
        MacOSOllamaInstaller._content_length(response)


def test_runtime_discovers_goldenson_managed_binary(tmp_path: Path) -> None:
    binary = tmp_path / "Ollama.app" / "Contents" / "Resources" / "ollama"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"binary")

    runtime = OllamaHTTPRuntime("http://127.0.0.1:11434", runtime_root=tmp_path)

    assert runtime.binary_path() == str(binary)
