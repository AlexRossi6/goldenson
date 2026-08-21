import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_create_and_retrieve_workspace(session: AsyncSession) -> None:
    service = WorkspaceService(session)

    created = await service.create_workspace(WorkspaceCreate(name="My Workspace"))
    await session.commit()

    fetched = await service.get_workspace(created.id)

    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "My Workspace"
