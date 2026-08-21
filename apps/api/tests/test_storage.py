import io
from pathlib import Path

import pytest
from fastapi import UploadFile

from goldenson_api.services.errors import StorageError
from goldenson_api.storage.local_storage import LocalStorage


@pytest.mark.asyncio
async def test_local_storage_generates_safe_key_and_writes_content(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "files")
    upload = UploadFile(filename="../../secret.txt", file=io.BytesIO(b"hello"))

    stored = await storage.store_upload(upload, "workspace-id", 100)

    assert stored.storage_key.startswith("workspace-id/")
    assert storage.resolve_file(stored.storage_key).read_bytes() == b"hello"
    assert not (tmp_path / "secret.txt").exists()


@pytest.mark.asyncio
async def test_local_storage_rejects_path_escape(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "files")

    with pytest.raises(StorageError):
        storage.resolve_file("../../secret.txt")
