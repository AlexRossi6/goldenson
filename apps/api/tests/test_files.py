import io
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.file_service import FileService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService
from goldenson_api.storage.local_storage import LocalStorage


@pytest.mark.asyncio
async def test_upload_file_with_workspace_and_optional_page(
    session: AsyncSession, tmp_path: Path
) -> None:
    workspace_service = WorkspaceService(session)
    page_service = PageService(session)
    file_service = FileService(session, LocalStorage(tmp_path / "files"))

    workspace = await workspace_service.create_workspace(WorkspaceCreate(name="Files Workspace"))
    page = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=None, title="Files", position=0)
    )

    attached = await file_service.upload_file(
        workspace.id,
        page.id,
        UploadFile(filename="diagram.png", file=io.BytesIO(b"image")),
    )
    detached = await file_service.upload_file(
        workspace.id,
        None,
        UploadFile(filename="notes.md", file=io.BytesIO(b"notes")),
    )
    await session.commit()

    files = await file_service.list_workspace_files(workspace.id)

    assert len(files) == 2
    assert attached.page_id == page.id
    assert detached.page_id is None
    assert file_service.download_path(attached).read_bytes() == b"image"


@pytest.mark.asyncio
async def test_upload_cleans_up_file_when_metadata_insert_fails(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = await WorkspaceService(session).create_workspace(
        WorkspaceCreate(name="Failure Workspace")
    )
    file_service = FileService(session, LocalStorage(tmp_path / "files"))
    monkeypatch.setattr(
        file_service._repository,
        "create",
        AsyncMock(side_effect=RuntimeError("database failure")),
    )

    with pytest.raises(RuntimeError, match="database failure"):
        await file_service.upload_file(
            workspace.id,
            None,
            UploadFile(filename="failed.txt", file=io.BytesIO(b"temporary")),
        )

    assert not any(path.is_file() for path in (tmp_path / "files").rglob("*"))


@pytest.mark.asyncio
async def test_delete_metadata_failure_preserves_stored_content(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = await WorkspaceService(session).create_workspace(
        WorkspaceCreate(name="Delete Failure Workspace")
    )
    file_service = FileService(session, LocalStorage(tmp_path / "files"))
    file_metadata = await file_service.upload_file(
        workspace.id,
        None,
        UploadFile(filename="keep.txt", file=io.BytesIO(b"preserve me")),
    )
    await session.commit()
    stored_path = file_service.download_path(file_metadata)
    monkeypatch.setattr(
        file_service._repository,
        "delete_by_id",
        AsyncMock(side_effect=RuntimeError("database failure")),
    )

    with pytest.raises(RuntimeError, match="database failure"):
        await file_service.delete_file(file_metadata.id)

    assert stored_path.read_bytes() == b"preserve me"
