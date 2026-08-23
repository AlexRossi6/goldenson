from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileMetadataRead(BaseModel):
    id: str
    workspace_id: str
    page_id: str | None
    name: str
    mime_type: str
    size: int
    index_status: str
    content_searchable: bool
    indexed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileMetadataListResponse(BaseModel):
    items: list[FileMetadataRead]
