from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.workspace import Workspace
from goldenson_api.db.repositories.workspace_repository import WorkspaceRepository
from goldenson_api.schemas.workspace import WorkspaceCreate


class WorkspaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = WorkspaceRepository(session)

    async def create_workspace(self, payload: WorkspaceCreate) -> Workspace:
        return await self._repository.create(name=payload.name)

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        return await self._repository.get_by_id(workspace_id)

    async def get_workspace_by_name(self, name: str) -> Workspace | None:
        return await self._repository.get_by_name(name)
