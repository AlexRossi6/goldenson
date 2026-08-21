from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class FileMetadataCreate(BaseModel):
    workspace_id: str
    page_id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)


class FileMetadataCreateRequest(BaseModel):
    page_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=512)
    mime_type: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)


class FileMetadataRead(BaseModel):
    id: str
    workspace_id: str
    page_id: str | None
    name: str
    storage_key: str
    mime_type: str
    size: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileMetadataListResponse(BaseModel):
    items: list[FileMetadataRead]
