from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.file_metadata import FileMetadata
from goldenson_api.db.models.knowledge import PageKnowledge
from goldenson_api.db.models.page import Page
from goldenson_api.schemas.index_health import (
    FileIndexCounts,
    IndexHealthStatus,
    PageIndexCounts,
    WorkspaceIndexHealth,
)


class IndexHealthService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def workspace_health(self, workspace_id: str) -> WorkspaceIndexHealth:
        page_ids = list(
            await self._session.scalars(select(Page.id).where(Page.workspace_id == workspace_id))
        )
        page_records = list(
            await self._session.scalars(
                select(PageKnowledge).where(PageKnowledge.workspace_id == workspace_id)
            )
        )
        page_status_by_id = {record.page_id: record.status for record in page_records}
        page_statuses = [page_status_by_id.get(page_id, "pending") for page_id in page_ids]
        file_records = list(
            await self._session.scalars(
                select(FileMetadata).where(FileMetadata.workspace_id == workspace_id)
            )
        )
        file_statuses = [file_metadata.index_status for file_metadata in file_records]

        pages = PageIndexCounts(
            total=len(page_statuses),
            ready=page_statuses.count("ready"),
            indexing=page_statuses.count("pending") + page_statuses.count("indexing"),
            stale=page_statuses.count("stale"),
            failed=page_statuses.count("failed"),
        )
        files = FileIndexCounts(
            total=len(file_statuses),
            ready=file_statuses.count("ready"),
            indexing=file_statuses.count("pending") + file_statuses.count("indexing"),
            stale=file_statuses.count("stale"),
            failed=file_statuses.count("failed"),
            metadata_only=file_statuses.count("metadata_only"),
        )
        active_statuses = page_statuses + [
            status for status in file_statuses if status != "metadata_only"
        ]
        status: IndexHealthStatus
        if "failed" in active_statuses:
            status = "failed"
        elif any(status in {"pending", "indexing"} for status in active_statuses):
            status = "indexing"
        elif "stale" in active_statuses:
            status = "stale"
        else:
            status = "ready"
        return WorkspaceIndexHealth(status=status, pages=pages, files=files)

    async def failed_page_ids(self, workspace_id: str) -> list[str]:
        return list(
            await self._session.scalars(
                select(PageKnowledge.page_id).where(
                    PageKnowledge.workspace_id == workspace_id,
                    PageKnowledge.status == "failed",
                )
            )
        )

    async def failed_file_ids(self, workspace_id: str) -> list[str]:
        return list(
            await self._session.scalars(
                select(FileMetadata.id).where(
                    FileMetadata.workspace_id == workspace_id,
                    FileMetadata.index_status == "failed",
                )
            )
        )
