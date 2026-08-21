from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.file_metadata import FileMetadata
from goldenson_api.db.repositories.file_repository import FileRepository
from goldenson_api.db.repositories.page_repository import PageRepository
from goldenson_api.db.repositories.workspace_repository import WorkspaceRepository
from goldenson_api.schemas.file_metadata import FileMetadataCreate
from goldenson_api.services.errors import BadRequestError, NotFoundError


class FileService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = FileRepository(session)
        self._workspace_repository = WorkspaceRepository(session)
        self._page_repository = PageRepository(session)

    async def create_file(self, payload: FileMetadataCreate) -> FileMetadata:
        workspace = await self._workspace_repository.get_by_id(payload.workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")

        if payload.page_id is not None:
            page = await self._page_repository.get_by_id(payload.page_id)
            if page is None:
                raise BadRequestError("page does not exist")
            if page.workspace_id != payload.workspace_id:
                raise BadRequestError("file page must belong to the same workspace")

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

    async def get_file(self, file_id: str) -> FileMetadata | None:
        return await self._repository.get_by_id(file_id)

    async def list_workspace_files(self, workspace_id: str) -> list[FileMetadata]:
        workspace = await self._workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")
        return await self._repository.list_for_workspace(workspace_id)

    async def delete_file(self, file_id: str) -> None:
        file_metadata = await self._repository.get_by_id(file_id)
        if file_metadata is None:
            raise NotFoundError("file metadata not found")

        deleted = await self._repository.delete_by_id(file_id)
        if not deleted:
            raise NotFoundError("file metadata not found")
