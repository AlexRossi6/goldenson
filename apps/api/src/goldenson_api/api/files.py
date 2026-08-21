from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.transaction import run_mutation
from goldenson_api.schemas.file_metadata import (
    FileMetadataCreate,
    FileMetadataCreateRequest,
    FileMetadataListResponse,
    FileMetadataRead,
)
from goldenson_api.services.errors import NotFoundError
from goldenson_api.services.file_service import FileService

router = APIRouter(tags=["Files"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/workspaces/{workspace_id}/files",
    response_model=FileMetadataListResponse,
    summary="List file metadata",
)
async def list_files(
    workspace_id: UUID,
    session: DbSession,
) -> FileMetadataListResponse:
    service = FileService(session)
    files = await service.list_workspace_files(str(workspace_id))
    return FileMetadataListResponse(items=[FileMetadataRead.model_validate(item) for item in files])


@router.post(
    "/workspaces/{workspace_id}/files",
    response_model=FileMetadataRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create file metadata",
)
async def create_file_metadata(
    workspace_id: UUID,
    payload: FileMetadataCreateRequest,
    session: DbSession,
) -> FileMetadataRead:
    service = FileService(session)

    async def action() -> FileMetadataRead:
        file_metadata = await service.create_file(
            FileMetadataCreate(
                workspace_id=str(workspace_id),
                page_id=None if payload.page_id is None else str(payload.page_id),
                name=payload.name,
                storage_key=payload.storage_key,
                mime_type=payload.mime_type,
                size=payload.size,
            )
        )
        return FileMetadataRead.model_validate(file_metadata)

    return await run_mutation(session, action)


@router.get("/files/{file_id}", response_model=FileMetadataRead, summary="Get file metadata")
async def get_file_metadata(
    file_id: UUID,
    session: DbSession,
) -> FileMetadataRead:
    service = FileService(session)
    file_metadata = await service.get_file(str(file_id))
    if file_metadata is None:
        raise NotFoundError("file metadata not found")
    return FileMetadataRead.model_validate(file_metadata)


@router.delete(
    "/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete file metadata",
)
async def delete_file_metadata(file_id: UUID, session: DbSession) -> None:
    service = FileService(session)

    async def action() -> None:
        await service.delete_file(str(file_id))

    await run_mutation(session, action)
