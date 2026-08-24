from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from goldenson_api.services.errors import FileTooLargeError, StorageError
from goldenson_api.storage.provider import StoredFile


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def _path_for_key(self, storage_key: str) -> Path:
        candidate = (self._root / storage_key).resolve()
        try:
            candidate.relative_to(self._root)
        except ValueError as exc:
            raise StorageError("invalid storage key") from exc
        return candidate

    async def store_upload(
        self, upload: UploadFile, workspace_id: str, max_size: int
    ) -> StoredFile:
        workspace_dir = self._path_for_key(workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        storage_key = f"{workspace_id}/{uuid4().hex}"
        destination = self._path_for_key(storage_key)
        temporary = destination.with_name(f".{destination.name}.upload")
        digest = hashlib.sha256()
        size = 0

        try:
            with temporary.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_size:
                        raise FileTooLargeError("file exceeds the maximum upload size")
                    digest.update(chunk)
                    output.write(chunk)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return StoredFile(storage_key=storage_key, size=size, sha256=digest.hexdigest())

    def store_content(self, content: bytes, workspace_id: str, max_size: int) -> StoredFile:
        if len(content) > max_size:
            raise FileTooLargeError("file exceeds the maximum upload size")
        workspace_dir = self._path_for_key(workspace_id)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        storage_key = f"{workspace_id}/{uuid4().hex}"
        destination = self._path_for_key(storage_key)
        temporary = destination.with_name(f".{destination.name}.upload")
        try:
            temporary.write_bytes(content)
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return StoredFile(
            storage_key=storage_key,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def resolve_file(self, storage_key: str) -> Path:
        path = self._path_for_key(storage_key)
        if not path.is_file():
            raise StorageError("file content is missing")
        return path

    def delete_file(self, storage_key: str) -> None:
        path = self._path_for_key(storage_key)
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise StorageError("file content is missing") from exc
        except OSError as exc:
            raise StorageError("file content could not be deleted") from exc
