from typing import Literal

from pydantic import BaseModel

IndexHealthStatus = Literal["ready", "indexing", "stale", "failed"]


class PageIndexCounts(BaseModel):
    total: int
    ready: int
    indexing: int
    stale: int
    failed: int


class FileIndexCounts(PageIndexCounts):
    metadata_only: int


class WorkspaceIndexHealth(BaseModel):
    status: IndexHealthStatus
    pages: PageIndexCounts
    files: FileIndexCounts


class RetryFailedIndexingResponse(BaseModel):
    queued: int
