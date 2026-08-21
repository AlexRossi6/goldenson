from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.page import Page
from goldenson_api.db.repositories.block_repository import BlockRepository
from goldenson_api.db.repositories.file_repository import FileRepository
from goldenson_api.db.repositories.page_repository import PageRepository
from goldenson_api.db.repositories.workspace_repository import WorkspaceRepository
from goldenson_api.schemas.page import PageCreate, PageUpdate, PageUpdateTitle
from goldenson_api.services.errors import (
    BadRequestError,
    ConcurrencyConflictError,
    NotFoundError,
)


class PageService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = PageRepository(session)
        self._block_repository = BlockRepository(session)
        self._file_repository = FileRepository(session)
        self._workspace_repository = WorkspaceRepository(session)

    async def create_page(self, payload: PageCreate) -> Page:
        workspace = await self._workspace_repository.get_by_id(payload.workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")

        if payload.parent_page_id is not None:
            parent = await self._repository.get_by_id(payload.parent_page_id)
            if parent is None:
                raise BadRequestError("parent page does not exist")
            if parent.workspace_id != payload.workspace_id:
                raise BadRequestError("parent page must belong to the same workspace")

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

    async def list_pages(self, workspace_id: str) -> list[Page]:
        workspace = await self._workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")
        return await self._repository.list_for_workspace(workspace_id)

    async def update_title(self, page_id: str, payload: PageUpdateTitle) -> Page:
        updated = await self._repository.update_title_with_version(
            page_id,
            title=payload.title,
            expected_version=payload.expected_version,
        )
        if updated is None:
            raise ConcurrencyConflictError("page update rejected due to stale version")
        return updated

    async def update_page(self, page_id: str, payload: PageUpdate, *, set_parent: bool) -> Page:
        page = await self._repository.get_by_id(page_id)
        if page is None:
            raise NotFoundError("page not found")

        if payload.title is None and payload.position is None and not set_parent:
            raise BadRequestError("no mutable page fields were provided")

        next_parent_id = page.parent_page_id
        if set_parent:
            next_parent_id = None if payload.parent_page_id is None else str(payload.parent_page_id)
            if next_parent_id == page.id:
                raise BadRequestError("a page cannot be its own parent")
            if next_parent_id is not None:
                parent = await self._repository.get_by_id(next_parent_id)
                if parent is None:
                    raise BadRequestError("parent page does not exist")
                if parent.workspace_id != page.workspace_id:
                    raise BadRequestError("parent page must belong to the same workspace")
                if await self._repository.is_descendant(page.id, next_parent_id):
                    raise BadRequestError("parent change would create a cycle")

        updated = await self._repository.update_with_version(
            page_id,
            expected_version=payload.version,
            title=payload.title,
            parent_page_id=next_parent_id,
            set_parent=set_parent,
            position=payload.position,
        )
        if updated is None:
            raise ConcurrencyConflictError("page update rejected due to stale version")
        return updated

    async def delete_page(self, page_id: str) -> None:
        page = await self._repository.get_by_id(page_id)
        if page is None:
            raise NotFoundError("page not found")

        pages = await self._repository.list_for_workspace(page.workspace_id)
        descendants = {page_id}
        changed = True
        while changed:
            changed = False
            for candidate in pages:
                if candidate.id not in descendants and candidate.parent_page_id in descendants:
                    descendants.add(candidate.id)
                    changed = True

        await self._block_repository.delete_for_pages(list(descendants))
        await self._file_repository.detach_from_pages(list(descendants))
        deleted = await self._repository.delete_subtree(list(descendants))
        if deleted != len(descendants):
            raise NotFoundError("page not found")

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
