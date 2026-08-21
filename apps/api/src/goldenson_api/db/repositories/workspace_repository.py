from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.workspace import Workspace


class WorkspaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str) -> Workspace:
        workspace = Workspace(name=name)
        self._session.add(workspace)
        await self._session.flush()
        return workspace

    async def get_by_id(self, workspace_id: str) -> Workspace | None:
        return await self._session.get(Workspace, workspace_id)

    async def get_by_name(self, name: str) -> Workspace | None:
        result = await self._session.execute(select(Workspace).where(Workspace.name == name))
        return result.scalar_one_or_none()
