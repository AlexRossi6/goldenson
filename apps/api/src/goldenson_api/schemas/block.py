from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BlockCreate(BaseModel):
    page_id: str
    type: str = Field(min_length=1, max_length=50)
    position: int = Field(ge=0)
    content: dict[str, object]


class BlockUpdateContent(BaseModel):
    content: dict[str, object]
    expected_version: int = Field(ge=1)


class BlockRead(BaseModel):
    id: str
    page_id: str
    type: str
    position: int
    content: dict[str, object]
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
