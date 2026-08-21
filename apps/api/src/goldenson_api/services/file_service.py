from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.file_metadata import FileMetadata
from goldenson_api.db.repositories.file_repository import FileRepository
from goldenson_api.schemas.file_metadata import FileMetadataCreate


class FileService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = FileRepository(session)

    async def create_file(self, payload: FileMetadataCreate) -> FileMetadata:
        return await self._repository.create(
            workspace_id=payload.workspace_id,
            page_id=payload.page_id,
            name=payload.name,
            storage_key=payload.storage_key,
            mime_type=payload.mime_type,
            size=payload.size,
        )

    async def get_by_storage_key(self, storage_key: str) -> FileMetadata | None:
        return await self._repository.get_by_storage_key(storage_key)

    async def list_workspace_files(self, workspace_id: str) -> list[FileMetadata]:
        return await self._repository.list_for_workspace(workspace_id)
