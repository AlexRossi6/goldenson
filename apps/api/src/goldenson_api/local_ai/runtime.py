from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

import httpx
from pydantic import BaseModel, Field


class InstalledModel(BaseModel):
    name: str
    size: int = Field(ge=0)


class PullProgress(BaseModel):
    status: str
    completed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)


class OllamaRuntime(Protocol):
    def binary_path(self) -> str | None: ...

    async def version(self) -> str: ...

    async def list_models(self) -> list[InstalledModel]: ...

    def pull_model(self, model_id: str) -> AsyncIterator[PullProgress]: ...

    async def remove_model(self, model_id: str) -> None: ...

    async def start(self) -> bool: ...


class OllamaHTTPRuntime:
    def __init__(
        self,
        base_url: str,
        *,
        runtime_root: Path | None = None,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._managed_binary = (
            runtime_root / "Ollama.app" / "Contents" / "Resources" / "ollama"
            if runtime_root is not None
            else None
        )
        self._timeout_seconds = timeout_seconds
        self._client = client

    def binary_path(self) -> str | None:
        if self._managed_binary is not None and self._managed_binary.is_file():
            return str(self._managed_binary)
        return shutil.which("ollama")

    async def version(self) -> str:
        response = await self._request("GET", "/api/version")
        value = response.json().get("version")
        if not isinstance(value, str):
            raise RuntimeError("Ollama returned an invalid version response")
        return value

    async def list_models(self) -> list[InstalledModel]:
        response = await self._request("GET", "/api/tags")
        models = response.json().get("models", [])
        if not isinstance(models, list):
            raise RuntimeError("Ollama returned an invalid model list")
        return [InstalledModel.model_validate(model) for model in models]

    async def pull_model(self, model_id: str) -> AsyncIterator[PullProgress]:
        if self._client is not None:
            async with self._client.stream(
                "POST", "/api/pull", json={"model": model_id, "stream": True}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield self._parse_pull_line(line)
            return

        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=None,
            trust_env=False,
        ) as client:
            async with client.stream(
                "POST", "/api/pull", json={"model": model_id, "stream": True}
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        yield self._parse_pull_line(line)

    async def remove_model(self, model_id: str) -> None:
        await self._request("DELETE", "/api/delete", json={"model": model_id})

    async def start(self) -> bool:
        binary = self.binary_path()
        if binary is None:
            return False
        subprocess.Popen(
            [binary, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        for _ in range(20):
            try:
                await self.version()
                return True
            except (httpx.HTTPError, RuntimeError):
                await asyncio.sleep(0.25)
        return False

    async def _request(
        self, method: str, path: str, *, json: dict[str, object] | None = None
    ) -> httpx.Response:
        if self._client is not None:
            response = await self._client.request(method, path, json=json)
        else:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                trust_env=False,
            ) as client:
                response = await client.request(method, path, json=json)
        response.raise_for_status()
        return response

    @staticmethod
    def _parse_pull_line(line: str) -> PullProgress:
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama returned invalid installation progress")
        error = payload.get("error")
        if isinstance(error, str):
            raise RuntimeError(error)
        return PullProgress.model_validate(payload)


def disk_free_bytes(path: Path) -> int | None:
    try:
        candidate = path.expanduser().resolve()
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return shutil.disk_usage(candidate).free
    except OSError:
        return None


def total_memory_bytes() -> int | None:
    try:
        import os

        page_size = os.sysconf("SC_PAGE_SIZE")
        page_count = os.sysconf("SC_PHYS_PAGES")
        if isinstance(page_size, int) and isinstance(page_count, int):
            return page_size * page_count
    except (OSError, ValueError):
        return None
    return None
