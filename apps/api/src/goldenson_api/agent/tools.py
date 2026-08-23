from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.agent.schemas import (
    TOOL_ARGUMENT_MODELS,
    TOOL_PERMISSIONS,
    CreateFileArgs,
    CreatePageArgs,
    CreateTaskArgs,
    DeletePageArgs,
    GetPageArgs,
    ListPagesArgs,
    MovePageArgs,
    QueryDatabaseArgs,
    ReadFileArgs,
    SearchWorkspaceArgs,
    ToolPermission,
    UpdatePageArgs,
)
from goldenson_api.retrieval.service import WorkspaceRetrievalService
from goldenson_api.schemas.block import BlockCreate, BlockRead
from goldenson_api.schemas.file_metadata import FileMetadataRead
from goldenson_api.schemas.page import PageCreate, PageRead, PageUpdate
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.errors import BadRequestError, NotFoundError
from goldenson_api.services.file_service import FileService
from goldenson_api.services.page_service import PageService

_TOOL_DESCRIPTIONS = {
    "search_workspace": "Search relevant workspace pages, blocks, and file metadata.",
    "get_page": "Get a page and its blocks by page ID.",
    "list_pages": "List pages in the current workspace.",
    "query_database": "Query a fixed entity using structured filters; never accepts SQL.",
    "read_file": "Read a text file by workspace file ID; never accepts a path.",
    "create_page": "Propose creating a page in the current workspace.",
    "update_page": "Propose changing a page title.",
    "create_task": "Propose creating a todo block on a page.",
    "move_page": "Propose moving a page in the hierarchy.",
    "create_file": "Propose creating a workspace text file.",
    "delete_page": "Propose deleting a page and its descendants.",
}


def tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": _TOOL_DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in TOOL_ARGUMENT_MODELS.items()
    ]


def validate_tool_arguments(name: str, arguments: dict[str, object]) -> BaseModel:
    model = TOOL_ARGUMENT_MODELS.get(name)
    if model is None:
        raise BadRequestError("unknown agent tool")
    try:
        return model.model_validate(arguments)
    except ValidationError as exc:
        raise BadRequestError("invalid agent tool arguments") from exc


def tool_permission(name: str) -> ToolPermission:
    permission = TOOL_PERMISSIONS.get(name)
    if permission is None:
        raise BadRequestError("unknown agent tool")
    return permission


def expected_effect(name: str, arguments: BaseModel) -> str:
    values = arguments.model_dump(mode="json")
    if name == "create_page":
        return f'Create page "{values["title"]}".'
    if name == "update_page":
        return f'Change page {values["page_id"]} title to "{values["title"]}".'
    if name == "create_task":
        return f'Create task "{values["text"]}" on page {values["page_id"]}.'
    if name == "move_page":
        return f"Move page {values['page_id']} to parent {values['parent_page_id']}."
    if name == "create_file":
        return f'Create workspace file "{values["name"]}".'
    if name == "delete_page":
        return f"Delete page {values['page_id']} and its descendants."
    return _TOOL_DESCRIPTIONS[name]


class AgentToolExecutor:
    def __init__(self, session: AsyncSession, workspace_id: str) -> None:
        self._session = session
        self._workspace_id = workspace_id
        self._pages = PageService(session)
        self._blocks = BlockService(session)
        self._files = FileService(session)
        self._retrieval = WorkspaceRetrievalService(session)

    async def execute(self, name: str, arguments: BaseModel) -> dict[str, object]:
        if name == "search_workspace":
            search_args = cast(SearchWorkspaceArgs, arguments)
            result = await self._retrieval.search(
                self._workspace_id, search_args.query, search_args.limit
            )
            return result.model_dump(mode="json")
        if name == "get_page":
            return await self._get_page(cast(GetPageArgs, arguments))
        if name == "list_pages":
            cast(ListPagesArgs, arguments)
            pages = await self._pages.list_pages(self._workspace_id)
            return {
                "items": [PageRead.model_validate(page).model_dump(mode="json") for page in pages]
            }
        if name == "query_database":
            return await self._query_database(cast(QueryDatabaseArgs, arguments))
        if name == "read_file":
            return await self._read_file(cast(ReadFileArgs, arguments))
        if name == "create_page":
            create_page_args = cast(CreatePageArgs, arguments)
            page = await self._pages.create_page(
                PageCreate(
                    workspace_id=self._workspace_id,
                    title=create_page_args.title,
                    parent_page_id=(
                        str(create_page_args.parent_page_id)
                        if create_page_args.parent_page_id
                        else None
                    ),
                    position=create_page_args.position,
                )
            )
            return PageRead.model_validate(page).model_dump(mode="json")
        if name == "update_page":
            update_page_args = cast(UpdatePageArgs, arguments)
            await self._require_workspace_page(str(update_page_args.page_id))
            page = await self._pages.update_page(
                str(update_page_args.page_id),
                PageUpdate(title=update_page_args.title, version=update_page_args.version),
                set_parent=False,
            )
            return PageRead.model_validate(page).model_dump(mode="json")
        if name == "create_task":
            create_task_args = cast(CreateTaskArgs, arguments)
            await self._require_workspace_page(str(create_task_args.page_id))
            block = await self._blocks.create_block(
                BlockCreate(
                    page_id=str(create_task_args.page_id),
                    type="todo",
                    position=create_task_args.position,
                    content={
                        "title": "",
                        "items": [
                            {
                                "id": "agent-task",
                                "text": create_task_args.text,
                                "completed": False,
                            }
                        ],
                    },
                )
            )
            return BlockRead.model_validate(block).model_dump(mode="json")
        if name == "move_page":
            move_page_args = cast(MovePageArgs, arguments)
            await self._require_workspace_page(str(move_page_args.page_id))
            page = await self._pages.update_page(
                str(move_page_args.page_id),
                PageUpdate(
                    parent_page_id=move_page_args.parent_page_id,
                    position=move_page_args.position,
                    version=move_page_args.version,
                ),
                set_parent=True,
            )
            return PageRead.model_validate(page).model_dump(mode="json")
        if name == "create_file":
            create_file_args = cast(CreateFileArgs, arguments)
            file_metadata = await self._files.create_text_file(
                self._workspace_id,
                create_file_args.name,
                create_file_args.content,
                str(create_file_args.page_id) if create_file_args.page_id else None,
            )
            return FileMetadataRead.model_validate(file_metadata).model_dump(mode="json")
        if name == "delete_page":
            delete_page_args = cast(DeletePageArgs, arguments)
            await self._require_workspace_page(str(delete_page_args.page_id))
            await self._pages.delete_page(str(delete_page_args.page_id))
            return {"deleted": True, "page_id": str(delete_page_args.page_id)}
        raise BadRequestError("unknown agent tool")

    async def _require_workspace_page(self, page_id: str) -> object:
        page = await self._pages.get_page(page_id)
        if page is None:
            raise NotFoundError("page not found")
        if page.workspace_id != self._workspace_id:
            raise BadRequestError("page does not belong to the agent workspace")
        return page

    async def _get_page(self, payload: GetPageArgs) -> dict[str, object]:
        page = await self._require_workspace_page(str(payload.page_id))
        blocks = await self._blocks.list_blocks(str(payload.page_id))
        return {
            "page": PageRead.model_validate(page).model_dump(mode="json"),
            "blocks": [BlockRead.model_validate(block).model_dump(mode="json") for block in blocks],
        }

    async def _query_database(self, payload: QueryDatabaseArgs) -> dict[str, object]:
        needle = payload.contains.casefold()
        if payload.entity == "pages":
            pages = await self._pages.list_pages(self._workspace_id)
            return {
                "items": [
                    PageRead.model_validate(page).model_dump(mode="json")
                    for page in pages
                    if not needle or needle in page.title.casefold()
                ]
            }
        if payload.entity == "files":
            files = await self._files.list_workspace_files(self._workspace_id)
            return {
                "items": [
                    FileMetadataRead.model_validate(item).model_dump(mode="json")
                    for item in files
                    if not needle or needle in item.name.casefold()
                ]
            }

        pages = await self._pages.list_pages(self._workspace_id)
        page_ids = {page.id for page in pages}
        if payload.page_id is not None:
            requested_page_id = str(payload.page_id)
            if requested_page_id not in page_ids:
                raise BadRequestError("page does not belong to the agent workspace")
            page_ids = {requested_page_id}
        blocks = []
        for page_id in page_ids:
            blocks.extend(await self._blocks.list_blocks(page_id))
        return {
            "items": [
                BlockRead.model_validate(block).model_dump(mode="json")
                for block in blocks
                if not needle or needle in json.dumps(block.content).casefold()
            ]
        }

    async def _read_file(self, payload: ReadFileArgs) -> dict[str, object]:
        file_metadata = await self._files.get_file(str(payload.file_id))
        if file_metadata is None:
            raise NotFoundError("file metadata not found")
        if file_metadata.workspace_id != self._workspace_id:
            raise BadRequestError("file does not belong to the agent workspace")
        suffix = Path(file_metadata.name).suffix.casefold()
        text_suffixes = {".txt", ".md", ".json", ".csv", ".py", ".ts", ".tsx", ".js"}
        if not file_metadata.mime_type.startswith("text/") and suffix not in text_suffixes:
            raise BadRequestError("only text workspace files can be read by the agent")
        path = self._files.download_path(file_metadata)
        content = path.read_text(encoding="utf-8")[:100_000]
        return {
            "file": FileMetadataRead.model_validate(file_metadata).model_dump(mode="json"),
            "content": content,
        }
