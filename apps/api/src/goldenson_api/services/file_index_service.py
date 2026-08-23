from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.file_metadata import FileMetadata
from goldenson_api.services.file_service import FileService, supports_file_content_search

_MAX_SEARCHABLE_TEXT_BYTES = 2 * 1024 * 1024
_FILE_INDEX_FAILURE_MESSAGE = "File content could not be prepared for search."


class FileIndexService:
    def __init__(self, session: AsyncSession, files: FileService | None = None) -> None:
        self._session = session
        self._files = files or FileService(session)

    async def mark_pending(self, file_id: str) -> int | None:
        file_metadata = await self._files.get_file(file_id)
        if file_metadata is None:
            return None
        if not supports_file_content_search(file_metadata.name, file_metadata.mime_type):
            file_metadata.index_status = "metadata_only"
            file_metadata.index_error = None
            await self._session.flush()
            return None
        file_metadata.index_generation += 1
        file_metadata.index_status = "pending"
        file_metadata.index_error = None
        await self._session.flush()
        return file_metadata.index_generation

    async def mark_indexing(self, file_id: str, expected_generation: int) -> bool:
        file_metadata = await self._files.get_file(file_id)
        if file_metadata is None or file_metadata.index_generation != expected_generation:
            return False
        file_metadata.index_status = "indexing"
        file_metadata.index_error = None
        await self._session.flush()
        return True

    async def mark_failed(self, file_id: str, expected_generation: int) -> None:
        file_metadata = await self._files.get_file(file_id)
        if file_metadata is None or file_metadata.index_generation != expected_generation:
            return
        file_metadata.index_status = "failed"
        file_metadata.index_error = _FILE_INDEX_FAILURE_MESSAGE
        await self._session.flush()

    async def index_file(self, file_id: str, expected_generation: int) -> FileMetadata | None:
        file_metadata = await self._files.get_file(file_id)
        if file_metadata is None or file_metadata.index_generation != expected_generation:
            return file_metadata
        if not supports_file_content_search(file_metadata.name, file_metadata.mime_type):
            file_metadata.index_status = "metadata_only"
            file_metadata.index_error = None
            await self._session.flush()
            return file_metadata
        if file_metadata.size > _MAX_SEARCHABLE_TEXT_BYTES:
            raise ValueError("supported text file exceeds the local indexing limit")

        path = self._files.download_path(file_metadata)
        content = await asyncio.to_thread(path.read_bytes)
        text = content.decode("utf-8")
        if "\x00" in text:
            raise ValueError("supported text file contains binary content")

        await self._session.refresh(file_metadata)
        if file_metadata.index_generation != expected_generation:
            return file_metadata
        file_metadata.search_text = text
        file_metadata.index_status = "ready"
        file_metadata.index_error = None
        file_metadata.indexed_at = datetime.now(UTC)
        await self._session.flush()
        return file_metadata
