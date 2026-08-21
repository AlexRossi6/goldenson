from typing import cast

from sqlalchemy import Result, delete, select
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
    ) -> FileMetadata:
        file_metadata = FileMetadata(
            workspace_id=workspace_id,
            page_id=page_id,
            name=name,
            storage_key=storage_key,
            mime_type=mime_type,
            size=size,
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

    async def delete_by_id(self, file_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object]],
            await self._session.execute(delete(FileMetadata).where(FileMetadata.id == file_id)),
        )
        return bool((result.rowcount or 0) == 1)
