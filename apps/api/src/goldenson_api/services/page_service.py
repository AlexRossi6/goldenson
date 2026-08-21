from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.page import Page
from goldenson_api.db.repositories.page_repository import PageRepository
from goldenson_api.schemas.page import PageCreate, PageUpdateTitle
from goldenson_api.services.errors import ConcurrencyConflictError


class PageService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = PageRepository(session)

    async def create_page(self, payload: PageCreate) -> Page:
        return await self._repository.create(
            workspace_id=payload.workspace_id,
            parent_page_id=payload.parent_page_id,
            title=payload.title,
            position=payload.position,
        )

    async def get_page(self, page_id: str) -> Page | None:
        return await self._repository.get_by_id(page_id)

    async def list_children(self, workspace_id: str, parent_page_id: str | None) -> list[Page]:
        return await self._repository.list_by_parent(workspace_id, parent_page_id)

    async def update_title(self, page_id: str, payload: PageUpdateTitle) -> Page:
        updated = await self._repository.update_title_with_version(
            page_id,
            title=payload.title,
            expected_version=payload.expected_version,
        )
        if updated is None:
            raise ConcurrencyConflictError("page update rejected due to stale version")
        return updated

    async def get_by_title_and_parent(
        self,
        workspace_id: str,
        title: str,
        parent_page_id: str | None,
    ) -> Page | None:
        return await self._repository.get_by_title_and_parent(
            workspace_id=workspace_id,
            title=title,
            parent_page_id=parent_page_id,
        )
