from __future__ import annotations

import asyncio
import os
import plistlib
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

import httpx

from goldenson_api.local_ai.schemas import (
    RuntimeInstallationState,
    RuntimeInstallProgressEvent,
)

OLLAMA_MACOS_DMG_URL = "https://ollama.com/download/Ollama.dmg"
OLLAMA_BUNDLE_ID = "com.electron.ollama"
OLLAMA_TEAM_ID = "3MU9H2V9Y9"
MAX_DOWNLOAD_BYTES = 1024**3


class OllamaInstaller(Protocol):
    def install(self) -> AsyncIterator[RuntimeInstallProgressEvent]: ...


class MacOSOllamaInstaller:
    def __init__(
        self,
        runtime_root: Path,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._runtime_root = runtime_root.expanduser().resolve()
        self._client = client

    async def install(self) -> AsyncIterator[RuntimeInstallProgressEvent]:
        self._runtime_root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="ollama-install-", dir=self._runtime_root.parent
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)
            image_path = temporary_root / "Ollama.dmg"
            mount_path = temporary_root / "mount"
            mount_path.mkdir()
            mounted = False
            try:
                async for event in self._download(image_path):
                    yield event
                yield self._event(
                    RuntimeInstallationState.VERIFYING,
                    "Verifying the official Ollama package...",
                )
                await asyncio.to_thread(self._mount, image_path, mount_path)
                mounted = True
                application_path = mount_path / "Ollama.app"
                await asyncio.to_thread(self._verify, application_path)
                yield self._event(
                    RuntimeInstallationState.INSTALLING,
                    "Installing Ollama for GoldenSon...",
                )
                await asyncio.to_thread(self._copy, application_path, temporary_root)
                yield self._event(
                    RuntimeInstallationState.READY,
                    "Ollama is installed and ready to start.",
                    progress=1,
                )
            except (httpx.HTTPError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
                yield self._event(
                    RuntimeInstallationState.FAILED,
                    str(exc)[:300] or "Ollama installation failed.",
                )
            finally:
                if mounted:
                    await asyncio.to_thread(self._unmount, mount_path)

    async def _download(self, destination: Path) -> AsyncIterator[RuntimeInstallProgressEvent]:
        if self._client is not None:
            async with self._client.stream("GET", OLLAMA_MACOS_DMG_URL) as response:
                async for event in self._write_download(response, destination):
                    yield event
            return
        async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
            async with client.stream("GET", OLLAMA_MACOS_DMG_URL) as response:
                async for event in self._write_download(response, destination):
                    yield event

    async def _write_download(
        self,
        response: httpx.Response,
        destination: Path,
    ) -> AsyncIterator[RuntimeInstallProgressEvent]:
        response.raise_for_status()
        total = self._content_length(response)
        downloaded = 0
        with destination.open("wb") as output:
            async for chunk in response.aiter_bytes():
                downloaded += len(chunk)
                if downloaded > MAX_DOWNLOAD_BYTES:
                    raise RuntimeError("Ollama download exceeded the allowed size")
                output.write(chunk)
                yield self._event(
                    RuntimeInstallationState.DOWNLOADING,
                    "Downloading Ollama...",
                    progress=downloaded / total if total else None,
                    downloaded_bytes=downloaded,
                    total_bytes=total,
                )

    @staticmethod
    def _content_length(response: httpx.Response) -> int | None:
        value = response.headers.get("content-length")
        if value is None:
            return None
        try:
            total = int(value)
        except ValueError as exc:
            raise RuntimeError("Ollama returned an invalid download size") from exc
        if total <= 0 or total > MAX_DOWNLOAD_BYTES:
            raise RuntimeError("Ollama download size is outside the allowed range")
        return total

    @staticmethod
    def _mount(image_path: Path, mount_path: Path) -> None:
        MacOSOllamaInstaller._run(
            "/usr/bin/hdiutil",
            "attach",
            "-readonly",
            "-nobrowse",
            "-mountpoint",
            str(mount_path),
            str(image_path),
        )

    @staticmethod
    def _unmount(mount_path: Path) -> None:
        subprocess.run(
            ["/usr/bin/hdiutil", "detach", str(mount_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

    @staticmethod
    def _verify(application_path: Path) -> None:
        info_path = application_path / "Contents" / "Info.plist"
        binary_path = application_path / "Contents" / "Resources" / "ollama"
        if not info_path.is_file() or not binary_path.is_file():
            raise RuntimeError("Ollama package has an unexpected structure")
        with info_path.open("rb") as info_file:
            info = plistlib.load(info_file)
        if info.get("CFBundleIdentifier") != OLLAMA_BUNDLE_ID:
            raise RuntimeError("Ollama package has an unexpected bundle identifier")
        MacOSOllamaInstaller._run(
            "/usr/bin/codesign", "--verify", "--deep", "--strict", str(application_path)
        )
        details = MacOSOllamaInstaller._run(
            "/usr/bin/codesign", "-dv", "--verbose=4", str(application_path)
        )
        if f"TeamIdentifier={OLLAMA_TEAM_ID}" not in details:
            raise RuntimeError("Ollama package is not signed by the expected developer")

    def _copy(self, application_path: Path, temporary_root: Path) -> None:
        staged_path = temporary_root / "Ollama-staged.app"
        shutil.copytree(application_path, staged_path, symlinks=True)
        destination = self._runtime_root / "Ollama.app"
        self._runtime_root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staged_path, destination)

    @staticmethod
    def _run(*arguments: str) -> str:
        result = subprocess.run(
            list(arguments),
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return f"{result.stdout}\n{result.stderr}"

    @staticmethod
    def _event(
        state: RuntimeInstallationState,
        message: str,
        *,
        progress: float | None = None,
        downloaded_bytes: int | None = None,
        total_bytes: int | None = None,
    ) -> RuntimeInstallProgressEvent:
        return RuntimeInstallProgressEvent(
            state=state,
            progress=progress,
            downloaded_bytes=downloaded_bytes,
            total_bytes=total_bytes,
            message=message,
        )
