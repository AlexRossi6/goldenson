import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.file_metadata import FileMetadataCreate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.file_service import FileService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_create_file_metadata_with_workspace_and_optional_page(session: AsyncSession) -> None:
    workspace_service = WorkspaceService(session)
    page_service = PageService(session)
    file_service = FileService(session)

    workspace = await workspace_service.create_workspace(WorkspaceCreate(name="Files Workspace"))
    page = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=None, title="Files", position=0)
    )

    attached = await file_service.create_file(
        FileMetadataCreate(
            workspace_id=workspace.id,
            page_id=page.id,
            name="diagram.png",
            storage_key="seed/diagram.png",
            mime_type="image/png",
            size=1234,
        )
    )
    detached = await file_service.create_file(
        FileMetadataCreate(
            workspace_id=workspace.id,
            page_id=None,
            name="notes.md",
            storage_key="seed/notes.md",
            mime_type="text/markdown",
            size=321,
        )
    )
    await session.commit()

    files = await file_service.list_workspace_files(workspace.id)

    assert len(files) == 2
    assert attached.page_id == page.id
    assert detached.page_id is None
