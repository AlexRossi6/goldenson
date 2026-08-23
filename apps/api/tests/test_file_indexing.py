from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.errors import StorageError
from goldenson_api.services.file_index_service import FileIndexService
from goldenson_api.services.file_service import FileService
from goldenson_api.services.workspace_service import WorkspaceService
from goldenson_api.storage.local_storage import LocalStorage


async def make_services(
    session: AsyncSession, tmp_path: Path
) -> tuple[str, FileService, FileIndexService]:
    workspace = await WorkspaceService(session).create_workspace(
        WorkspaceCreate(name="File indexing")
    )
    files = FileService(session, LocalStorage(tmp_path / "files"))
    return workspace.id, files, FileIndexService(session, files)


async def test_supported_utf8_text_becomes_searchable(
    session: AsyncSession, tmp_path: Path
) -> None:
    workspace_id, files, index = await make_services(session, tmp_path)
    file_metadata = await files.upload_file(
        workspace_id,
        None,
        UploadFile(
            filename="notes.md",
            file=io.BytesIO(b"local inference benchmark"),
            headers=Headers({"content-type": "text/markdown"}),
        ),
    )

    indexed = await index.index_file(file_metadata.id, file_metadata.index_generation)
    await session.commit()

    assert indexed is not None
    assert indexed.index_status == "ready"
    assert indexed.search_text == "local inference benchmark"
    assert indexed.indexed_at is not None


async def test_pdf_is_stored_without_claiming_content_search(
    session: AsyncSession, tmp_path: Path
) -> None:
    workspace_id, files, _ = await make_services(session, tmp_path)
    file_metadata = await files.upload_file(
        workspace_id,
        None,
        UploadFile(
            filename="reference.pdf",
            file=io.BytesIO(b"%PDF-1.4 placeholder"),
            headers=Headers({"content-type": "application/pdf"}),
        ),
    )
    await session.commit()

    assert files.download_path(file_metadata).read_bytes().startswith(b"%PDF")
    assert file_metadata.index_status == "metadata_only"
    assert file_metadata.search_text is None


async def test_malformed_text_reaches_terminal_failed_state(
    session: AsyncSession, tmp_path: Path
) -> None:
    workspace_id, files, index = await make_services(session, tmp_path)
    file_metadata = await files.upload_file(
        workspace_id,
        None,
        UploadFile(
            filename="broken.txt",
            file=io.BytesIO(b"\xff\xfe"),
            headers=Headers({"content-type": "text/plain"}),
        ),
    )

    with pytest.raises(UnicodeDecodeError):
        await index.index_file(file_metadata.id, file_metadata.index_generation)
    await index.mark_failed(file_metadata.id, file_metadata.index_generation)
    await session.commit()

    assert file_metadata.index_status == "failed"
    assert file_metadata.index_error == "File content could not be prepared for search."
    assert file_metadata.search_text is None


async def test_stale_file_generation_cannot_replace_newer_state(
    session: AsyncSession, tmp_path: Path
) -> None:
    workspace_id, files, index = await make_services(session, tmp_path)
    file_metadata = await files.upload_file(
        workspace_id,
        None,
        UploadFile(
            filename="notes.txt",
            file=io.BytesIO(b"current searchable content"),
            headers=Headers({"content-type": "text/plain"}),
        ),
    )
    stale_generation = file_metadata.index_generation
    current_generation = await index.mark_pending(file_metadata.id)
    assert current_generation is not None
    current = await index.index_file(file_metadata.id, current_generation)
    stale = await index.index_file(file_metadata.id, stale_generation)
    await session.commit()

    assert current is not None
    assert stale is not None
    assert stale.index_status == "ready"
    assert stale.index_generation == current_generation
    assert stale.search_text == "current searchable content"


async def test_failed_file_refresh_preserves_previous_searchable_content(
    session: AsyncSession, tmp_path: Path
) -> None:
    workspace_id, files, index = await make_services(session, tmp_path)
    file_metadata = await files.upload_file(
        workspace_id,
        None,
        UploadFile(
            filename="notes.txt",
            file=io.BytesIO(b"preserved searchable content"),
            headers=Headers({"content-type": "text/plain"}),
        ),
    )
    await index.index_file(file_metadata.id, file_metadata.index_generation)
    files.download_path(file_metadata).unlink()
    generation = await index.mark_pending(file_metadata.id)
    assert generation is not None

    with pytest.raises(StorageError):
        await index.index_file(file_metadata.id, generation)
    await index.mark_failed(file_metadata.id, generation)
    await session.commit()

    assert file_metadata.index_status == "failed"
    assert file_metadata.content_searchable is True
    assert file_metadata.search_text == "preserved searchable content"
