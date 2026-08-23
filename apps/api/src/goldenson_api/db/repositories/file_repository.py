from datetime import datetime
from typing import cast

from sqlalchemy import Result, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.file_metadata import FileMetadata


class FileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        workspace_id: str,
        name: str,
        storage_key: str,
        mime_type: str,
        size: int,
        page_id: str | None = None,
        index_status: str = "metadata_only",
        search_text: str | None = None,
        content_hash: str | None = None,
        index_generation: int = 0,
        indexed_at: datetime | None = None,
    ) -> FileMetadata:
        file_metadata = FileMetadata(
            workspace_id=workspace_id,
            page_id=page_id,
            name=name,
            storage_key=storage_key,
            mime_type=mime_type,
            size=size,
            index_status=index_status,
            search_text=search_text,
            content_hash=content_hash,
            index_generation=index_generation,
            indexed_at=indexed_at,
        )
        self._session.add(file_metadata)
        await self._session.flush()
        return file_metadata

    async def get_by_storage_key(self, storage_key: str) -> FileMetadata | None:
        stmt = select(FileMetadata).where(FileMetadata.storage_key == storage_key)
        result: Result[tuple[FileMetadata]] = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, file_id: str) -> FileMetadata | None:
        return await self._session.get(FileMetadata, file_id)

    async def list_for_workspace(self, workspace_id: str) -> list[FileMetadata]:
        stmt = (
            select(FileMetadata)
            .where(FileMetadata.workspace_id == workspace_id)
            .order_by(FileMetadata.created_at.asc())
        )
        result: Result[tuple[FileMetadata]] = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_page(self, page_id: str) -> list[FileMetadata]:
        stmt = (
            select(FileMetadata)
            .where(FileMetadata.page_id == page_id)
            .order_by(FileMetadata.created_at.asc())
        )
        result: Result[tuple[FileMetadata]] = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def detach_from_pages(self, page_ids: list[str]) -> int:
        if not page_ids:
            return 0
        result = cast(
            CursorResult[tuple[object]],
            await self._session.execute(
                update(FileMetadata).where(FileMetadata.page_id.in_(page_ids)).values(page_id=None)
            ),
        )
        return int(result.rowcount or 0)

    async def delete_by_id(self, file_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object]],
            await self._session.execute(delete(FileMetadata).where(FileMetadata.id == file_id)),
        )
        return bool((result.rowcount or 0) == 1)
