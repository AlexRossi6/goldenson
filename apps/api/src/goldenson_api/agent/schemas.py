from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolPermission(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchWorkspaceArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=6, ge=1, le=10)


class GetPageArgs(ToolArgs):
    page_id: UUID


class ListPagesArgs(ToolArgs):
    pass


class QueryDatabaseArgs(ToolArgs):
    entity: Literal["pages", "blocks", "files"]
    contains: str = Field(default="", max_length=255)
    page_id: UUID | None = None


class ReadFileArgs(ToolArgs):
    file_id: UUID


class CreatePageArgs(ToolArgs):
    title: str = Field(min_length=1, max_length=255)
    parent_page_id: UUID | None = None
    position: int = Field(default=0, ge=0)


class UpdatePageArgs(ToolArgs):
    page_id: UUID
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)


class CreateTaskArgs(ToolArgs):
    page_id: UUID
    text: str = Field(min_length=1, max_length=2000)
    position: int = Field(default=0, ge=0)


class MovePageArgs(ToolArgs):
    page_id: UUID
    version: int = Field(ge=1)
    parent_page_id: UUID | None = None
    position: int = Field(ge=0)


class CreateFileArgs(ToolArgs):
    name: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+$")
    content: str = Field(max_length=100_000)
    page_id: UUID | None = None


class DeletePageArgs(ToolArgs):
    page_id: UUID


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class ApprovalDecision(BaseModel):
    approved: bool


class ToolProposal(BaseModel):
    tool_call_id: str
    tool_name: str
    permission: ToolPermission
    arguments: dict[str, object]
    expected_effect: str


TOOL_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "search_workspace": SearchWorkspaceArgs,
    "get_page": GetPageArgs,
    "list_pages": ListPagesArgs,
    "query_database": QueryDatabaseArgs,
    "read_file": ReadFileArgs,
    "create_page": CreatePageArgs,
    "update_page": UpdatePageArgs,
    "create_task": CreateTaskArgs,
    "move_page": MovePageArgs,
    "create_file": CreateFileArgs,
    "delete_page": DeletePageArgs,
}

TOOL_PERMISSIONS = {
    "search_workspace": ToolPermission.READ,
    "get_page": ToolPermission.READ,
    "list_pages": ToolPermission.READ,
    "query_database": ToolPermission.READ,
    "read_file": ToolPermission.READ,
    "create_page": ToolPermission.WRITE,
    "update_page": ToolPermission.WRITE,
    "create_task": ToolPermission.WRITE,
    "move_page": ToolPermission.WRITE,
    "create_file": ToolPermission.WRITE,
    "delete_page": ToolPermission.DESTRUCTIVE,
}
