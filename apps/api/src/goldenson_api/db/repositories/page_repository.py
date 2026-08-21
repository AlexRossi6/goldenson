from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Result, delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.page import Page


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        workspace_id: str,
        title: str,
        position: int,
        parent_page_id: str | None = None,
    ) -> Page:
        page = Page(
            workspace_id=workspace_id,
            parent_page_id=parent_page_id,
            title=title,
            position=position,
        )
        self._session.add(page)
        await self._session.flush()
        return page

    async def get_by_id(self, page_id: str) -> Page | None:
        return await self._session.get(Page, page_id)

    async def get_by_title_and_parent(
        self,
        workspace_id: str,
        title: str,
        parent_page_id: str | None,
    ) -> Page | None:
        stmt = select(Page).where(
            Page.workspace_id == workspace_id,
            Page.parent_page_id == parent_page_id,
            Page.title == title,
        )
        result: Result[tuple[Page]] = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_parent(self, workspace_id: str, parent_page_id: str | None) -> list[Page]:
        stmt = (
            select(Page)
            .where(Page.workspace_id == workspace_id, Page.parent_page_id == parent_page_id)
            .order_by(Page.position.asc(), Page.created_at.asc())
        )
        result: Result[tuple[Page]] = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_workspace(self, workspace_id: str) -> list[Page]:
        stmt = (
            select(Page)
            .where(Page.workspace_id == workspace_id)
            .order_by(Page.parent_page_id.asc(), Page.position.asc(), Page.created_at.asc())
        )
        result: Result[tuple[Page]] = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def has_children(self, page_id: str) -> bool:
        stmt = select(func.count(Page.id)).where(Page.parent_page_id == page_id)
        count = await self._session.scalar(stmt)
        return bool((count or 0) > 0)

    async def delete_by_id(self, page_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object]],
            await self._session.execute(delete(Page).where(Page.id == page_id)),
        )
        return bool((result.rowcount or 0) == 1)

    async def is_descendant(self, page_id: str, candidate_ancestor_id: str) -> bool:
        current = await self.get_by_id(candidate_ancestor_id)
        while current is not None and current.parent_page_id is not None:
            if current.parent_page_id == page_id:
                return True
            current = await self.get_by_id(current.parent_page_id)
        return False

    async def update_title_with_version(
        self, page_id: str, *, title: str, expected_version: int
    ) -> Page | None:
        stmt = (
            update(Page)
            .where(Page.id == page_id, Page.version == expected_version)
            .values(title=title, version=expected_version + 1, updated_at=_utc_now())
        )
        result = cast(CursorResult[tuple[object]], await self._session.execute(stmt))
        updated_rows = result.rowcount or 0
        if updated_rows != 1:
            return None

        await self._session.flush()
        return await self.get_by_id(page_id)

    async def update_with_version(
        self,
        page_id: str,
        *,
        expected_version: int,
        title: str | None,
        parent_page_id: str | None,
        set_parent: bool,
        position: int | None,
    ) -> Page | None:
        values: dict[str, object] = {
            "version": expected_version + 1,
            "updated_at": _utc_now(),
        }
        if title is not None:
            values["title"] = title
        if set_parent:
            values["parent_page_id"] = parent_page_id
        if position is not None:
            values["position"] = position

        stmt = (
            update(Page)
            .where(Page.id == page_id, Page.version == expected_version)
            .values(**values)
        )
        result = cast(CursorResult[tuple[object]], await self._session.execute(stmt))
        if (result.rowcount or 0) != 1:
            return None

        await self._session.flush()
        return await self.get_by_id(page_id)
