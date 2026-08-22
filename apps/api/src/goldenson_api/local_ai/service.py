from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.repositories.local_ai_settings_repository import (
    LocalAISettingsRepository,
)
from goldenson_api.local_ai.catalog import MODEL_CATALOG, MODEL_CATALOG_BY_ID, CatalogModel
from goldenson_api.local_ai.runtime import (
    InstalledModel,
    OllamaRuntime,
    disk_free_bytes,
    total_memory_bytes,
)
from goldenson_api.local_ai.schemas import (
    InstallationState,
    InstallProgressEvent,
    LocalAIStatus,
    ModelStatus,
    RuntimeStatus,
)
from goldenson_api.services.errors import BadRequestError


@dataclass
class InstallationJob:
    state: InstallationState
    cancel_event: asyncio.Event
    progress: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    error: str | None = None


_installation_jobs: dict[str, InstallationJob] = {}
_installation_lock = asyncio.Lock()


class LocalAIService:
    def __init__(
        self,
        session: AsyncSession,
        runtime: OllamaRuntime,
        storage_root: Path,
        *,
        disk_free: Callable[[Path], int | None] = disk_free_bytes,
        total_memory: Callable[[], int | None] = total_memory_bytes,
    ) -> None:
        self._session = session
        self._runtime = runtime
        self._storage_root = storage_root
        self._disk_free = disk_free
        self._total_memory = total_memory
        self._settings = LocalAISettingsRepository(session)

    async def get_status(self) -> LocalAIStatus:
        runtime_status, installed = await self._runtime_snapshot()
        settings = await self._settings.get()
        installed_by_id = {model.name: model for model in installed}
        selected_model = settings.selected_model

        if selected_model not in installed_by_id:
            selected_model = self._automatic_selection(installed_by_id)
            if selected_model != settings.selected_model:
                await self._settings.select_model(selected_model)
                await self._session.commit()

        recommended = self._recommended_model()
        models = [
            self._model_status(
                catalog_model,
                installed_by_id,
                selected_model,
                recommended.id,
            )
            for catalog_model in MODEL_CATALOG
        ]
        return LocalAIStatus(
            runtime=runtime_status,
            selected_model=selected_model,
            models=models,
            disk_free_bytes=self._disk_free(self._storage_root),
        )

    async def start_runtime(self) -> RuntimeStatus:
        if self._runtime.binary_path() is None:
            return RuntimeStatus(
                installed=False,
                reachable=False,
                usable=False,
                error="Ollama is not installed. Install Ollama, then try again.",
            )
        started = await self._runtime.start()
        if not started:
            return RuntimeStatus(
                installed=True,
                reachable=False,
                usable=False,
                error="Ollama could not be started.",
            )
        status, _ = await self._runtime_snapshot()
        return status

    async def select_model(self, model_id: str) -> LocalAIStatus:
        self._catalog_model(model_id)
        runtime_status, installed = await self._runtime_snapshot()
        if not runtime_status.reachable:
            raise BadRequestError("Ollama is not available")
        if model_id not in {model.name for model in installed}:
            raise BadRequestError("model is not installed")
        await self._settings.select_model(model_id)
        await self._session.commit()
        return await self.get_status()

    async def selected_ready_model(self) -> str:
        status = await self.get_status()
        if not status.runtime.usable or status.selected_model is None:
            raise BadRequestError("no local AI model is ready")
        selected = next(
            (model for model in status.models if model.id == status.selected_model), None
        )
        if selected is None or selected.state != InstallationState.READY:
            raise BadRequestError("selected local AI model is unavailable")
        return selected.id

    async def install_model(self, model_id: str) -> AsyncIterator[InstallProgressEvent]:
        catalog_model = self._catalog_model(model_id)
        async with _installation_lock:
            existing = _installation_jobs.get(model_id)
            if existing and existing.state in {
                InstallationState.CHECKING,
                InstallationState.DOWNLOADING,
                InstallationState.INSTALLING,
            }:
                raise BadRequestError("model installation is already running")
            job = InstallationJob(InstallationState.CHECKING, asyncio.Event())
            _installation_jobs[model_id] = job

        yield self._event(model_id, job, "Checking local runtime and disk space...")
        try:
            runtime_status, installed = await self._runtime_snapshot()
            if not runtime_status.reachable:
                raise RuntimeError(runtime_status.error or "Ollama is unavailable")
            if model_id in {model.name for model in installed}:
                job.state = InstallationState.READY
                yield self._event(model_id, job, "Model is already installed.")
                return

            free_bytes = self._disk_free(self._storage_root)
            if free_bytes is not None and free_bytes < catalog_model.required_disk_bytes:
                raise RuntimeError("Insufficient disk space for this model")

            job.state = InstallationState.DOWNLOADING
            yield self._event(model_id, job, "Downloading model...")
            async for progress in self._runtime.pull_model(model_id):
                if job.cancel_event.is_set():
                    job.state = InstallationState.CANCELLED
                    yield self._event(model_id, job, "Installation cancelled.")
                    return
                job.downloaded_bytes = progress.completed
                job.total_bytes = progress.total
                if progress.completed is not None and progress.total:
                    job.progress = min(1.0, progress.completed / progress.total)
                if progress.status in {"verifying sha256 digest", "writing manifest", "success"}:
                    job.state = InstallationState.INSTALLING
                yield self._event(model_id, job, progress.status)

            if job.cancel_event.is_set():
                job.state = InstallationState.CANCELLED
                yield self._event(model_id, job, "Installation cancelled.")
                return
            installed_after = await self._runtime.list_models()
            if model_id not in {model.name for model in installed_after}:
                raise RuntimeError("Ollama did not report the model as installed")
            job.state = InstallationState.READY
            job.progress = 1.0
            yield self._event(model_id, job, "Model ready.")
        except (httpx.HTTPError, RuntimeError) as exc:
            job.state = InstallationState.FAILED
            job.error = str(exc)[:300]
            yield self._event(model_id, job, job.error)

    def cancel_installation(self, model_id: str) -> bool:
        self._catalog_model(model_id)
        job = _installation_jobs.get(model_id)
        if job is None or job.state not in {
            InstallationState.CHECKING,
            InstallationState.DOWNLOADING,
            InstallationState.INSTALLING,
        }:
            return False
        job.cancel_event.set()
        return True

    async def remove_model(self, model_id: str) -> LocalAIStatus:
        self._catalog_model(model_id)
        settings = await self._settings.get()
        if settings.selected_model == model_id:
            raise BadRequestError("select another model before removing the current model")
        _, installed = await self._runtime_snapshot()
        if model_id not in {model.name for model in installed}:
            raise BadRequestError("model is not installed")
        await self._runtime.remove_model(model_id)
        return await self.get_status()

    async def _runtime_snapshot(self) -> tuple[RuntimeStatus, list[InstalledModel]]:
        binary_installed = self._runtime.binary_path() is not None
        try:
            version = await self._runtime.version()
            models = await self._runtime.list_models()
            return (
                RuntimeStatus(
                    installed=binary_installed,
                    reachable=True,
                    usable=True,
                    version=version,
                ),
                list(models),
            )
        except (httpx.HTTPError, RuntimeError):
            return (
                RuntimeStatus(
                    installed=binary_installed,
                    reachable=False,
                    usable=False,
                    error=(
                        "Ollama is installed but not running."
                        if binary_installed
                        else "Ollama is not installed."
                    ),
                ),
                [],
            )

    def _model_status(
        self,
        model: CatalogModel,
        installed_by_id: dict[str, InstalledModel],
        selected_model: str | None,
        recommended_id: str,
    ) -> ModelStatus:
        installed = installed_by_id.get(model.id)
        job = _installation_jobs.get(model.id)
        state = InstallationState.READY if installed else InstallationState.AVAILABLE
        if job is not None and job.state != InstallationState.READY:
            state = job.state
        installed_size = getattr(installed, "size", None)
        return ModelStatus(
            id=model.id,
            name=model.name,
            size_bytes=model.size_bytes,
            installed_size_bytes=installed_size if isinstance(installed_size, int) else None,
            required_disk_bytes=model.required_disk_bytes,
            role=model.role,
            state=state,
            selected=selected_model == model.id,
            recommended=recommended_id == model.id,
            progress=job.progress if job else None,
            downloaded_bytes=job.downloaded_bytes if job else None,
            total_bytes=job.total_bytes if job else None,
            error=job.error if job else None,
        )

    def _recommended_model(self) -> CatalogModel:
        memory = self._total_memory()
        if memory is None:
            return MODEL_CATALOG[0]
        eligible = [model for model in MODEL_CATALOG if model.minimum_memory_bytes <= memory]
        return eligible[-1] if eligible else MODEL_CATALOG[0]

    def _automatic_selection(self, installed_by_id: dict[str, InstalledModel]) -> str | None:
        recommended = self._recommended_model()
        if recommended.id in installed_by_id:
            return recommended.id
        return next((model.id for model in MODEL_CATALOG if model.id in installed_by_id), None)

    @staticmethod
    def _catalog_model(model_id: str) -> CatalogModel:
        model = MODEL_CATALOG_BY_ID.get(model_id)
        if model is None:
            raise BadRequestError("model is not in the supported catalog")
        return model

    @staticmethod
    def _event(model_id: str, job: InstallationJob, message: str | None) -> InstallProgressEvent:
        return InstallProgressEvent(
            state=job.state,
            model_id=model_id,
            progress=job.progress,
            downloaded_bytes=job.downloaded_bytes,
            total_bytes=job.total_bytes,
            message=message,
        )
