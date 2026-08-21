from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PageCreate(BaseModel):
    workspace_id: str
    parent_page_id: str | None = None
    title: str = Field(min_length=1, max_length=255)
    position: int = Field(ge=0)


class PageUpdateTitle(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    expected_version: int = Field(ge=1)


class PageRead(BaseModel):
    id: str
    workspace_id: str
    parent_page_id: str | None
    title: str
    position: int
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
