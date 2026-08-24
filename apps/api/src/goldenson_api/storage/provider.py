from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import UploadFile


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    size: int
    sha256: str


class StorageProvider(Protocol):
    async def store_upload(
        self, upload: UploadFile, workspace_id: str, max_size: int
    ) -> StoredFile: ...

    def store_content(self, content: bytes, workspace_id: str, max_size: int) -> StoredFile: ...

    def resolve_file(self, storage_key: str) -> Path: ...

    def delete_file(self, storage_key: str) -> None: ...
