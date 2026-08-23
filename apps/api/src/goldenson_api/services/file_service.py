from datetime import UTC, datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.core.config import get_settings
from goldenson_api.db.models.file_metadata import FileMetadata
from goldenson_api.db.repositories.file_repository import FileRepository
from goldenson_api.db.repositories.page_repository import PageRepository
from goldenson_api.db.repositories.workspace_repository import WorkspaceRepository
from goldenson_api.services.errors import BadRequestError, NotFoundError
from goldenson_api.storage.local_storage import LocalStorage

_TEXT_MIME_TYPES = {"application/json", "application/xml"}
_TEXT_SUFFIXES = {".csv", ".json", ".log", ".md", ".markdown", ".txt", ".xml"}


def supports_file_content_search(name: str, mime_type: str) -> bool:
    return (
        mime_type.casefold().startswith("text/")
        or mime_type.casefold() in _TEXT_MIME_TYPES
        or Path(name).suffix.casefold() in _TEXT_SUFFIXES
    )


class FileService:
    def __init__(self, session: AsyncSession, storage: LocalStorage | None = None) -> None:
        self._repository = FileRepository(session)
        self._workspace_repository = WorkspaceRepository(session)
        self._page_repository = PageRepository(session)
        settings = get_settings()
        self._storage = storage or LocalStorage(settings.storage_root)
        self._max_upload_size = settings.max_upload_size

    async def upload_file(
        self,
        workspace_id: str,
        page_id: str | None,
        upload: UploadFile,
    ) -> FileMetadata:
        workspace = await self._workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")

        if page_id is not None:
            page = await self._page_repository.get_by_id(page_id)
            if page is None:
                raise BadRequestError("page does not exist")
            if page.workspace_id != workspace_id:
                raise BadRequestError("file page must belong to the same workspace")

        stored = await self._storage.store_upload(upload, workspace_id, self._max_upload_size)
        supports_content_search = supports_file_content_search(
            upload.filename or "untitled", upload.content_type or "application/octet-stream"
        )
        try:
            return await self._repository.create(
                workspace_id=workspace_id,
                page_id=page_id,
                name=upload.filename or "untitled",
                storage_key=stored.storage_key,
                mime_type=upload.content_type or "application/octet-stream",
                size=stored.size,
                index_status="pending" if supports_content_search else "metadata_only",
                content_hash=stored.sha256,
                index_generation=1 if supports_content_search else 0,
            )
        except Exception:
            self._storage.delete_file(stored.storage_key)
            raise

    async def create_text_file(
        self,
        workspace_id: str,
        name: str,
        content: str,
        page_id: str | None,
    ) -> FileMetadata:
        workspace = await self._workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")
        if page_id is not None:
            page = await self._page_repository.get_by_id(page_id)
            if page is None or page.workspace_id != workspace_id:
                raise BadRequestError("file page must belong to the same workspace")

        stored = self._storage.store_content(
            content.encode("utf-8"), workspace_id, self._max_upload_size
        )
        try:
            return await self._repository.create(
                workspace_id=workspace_id,
                page_id=page_id,
                name=name,
                storage_key=stored.storage_key,
                mime_type="text/plain",
                size=stored.size,
                index_status="ready",
                search_text=content,
                content_hash=stored.sha256,
                index_generation=1,
                indexed_at=datetime.now(UTC),
            )
        except Exception:
            self._storage.delete_file(stored.storage_key)
            raise

    def download_path(self, file_metadata: FileMetadata) -> Path:
        return self._storage.resolve_file(file_metadata.storage_key)

    def cleanup_file(self, storage_key: str) -> None:
        self._storage.delete_file(storage_key)

    async def get_by_storage_key(self, storage_key: str) -> FileMetadata | None:
        return await self._repository.get_by_storage_key(storage_key)

    async def get_file(self, file_id: str) -> FileMetadata | None:
        return await self._repository.get_by_id(file_id)

    async def list_workspace_files(self, workspace_id: str) -> list[FileMetadata]:
        workspace = await self._workspace_repository.get_by_id(workspace_id)
        if workspace is None:
            raise NotFoundError("workspace not found")
        return await self._repository.list_for_workspace(workspace_id)

    async def list_page_files(self, page_id: str) -> list[FileMetadata]:
        page = await self._page_repository.get_by_id(page_id)
        if page is None:
            raise NotFoundError("page not found")
        return await self._repository.list_for_page(page_id)

    async def detach_from_pages(self, page_ids: list[str]) -> None:
        await self._repository.detach_from_pages(page_ids)

    async def delete_file(self, file_id: str) -> None:
        file_metadata = await self._repository.get_by_id(file_id)
        if file_metadata is None:
            raise NotFoundError("file metadata not found")

        self._storage.delete_file(file_metadata.storage_key)
        deleted = await self._repository.delete_by_id(file_id)
        if not deleted:
            raise NotFoundError("file metadata not found")
