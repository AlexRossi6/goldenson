from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.knowledge_tasks import queue_file_index
from goldenson_api.api.transaction import run_mutation
from goldenson_api.schemas.file_metadata import FileMetadataListResponse, FileMetadataRead
from goldenson_api.services.errors import NotFoundError
from goldenson_api.services.file_index_service import FileIndexService
from goldenson_api.services.file_service import FileService

router = APIRouter(tags=["Files"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
UploadPart = File(...)
PagePart = Form(default=None)


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
    summary="Upload file",
)
async def upload_file(
    workspace_id: UUID,
    session: DbSession,
    background_tasks: BackgroundTasks,
    upload: UploadFile = UploadPart,
    page_id: UUID | None = PagePart,
) -> FileMetadataRead:
    service = FileService(session)
    uploaded: list[str] = []
    pending_generations: list[int] = []

    async def action() -> FileMetadataRead:
        file_metadata = await service.upload_file(
            workspace_id=str(workspace_id),
            page_id=None if page_id is None else str(page_id),
            upload=upload,
        )
        uploaded.append(file_metadata.storage_key)
        if file_metadata.index_status == "pending":
            pending_generations.append(file_metadata.index_generation)
        return FileMetadataRead.model_validate(file_metadata)

    async def cleanup() -> None:
        if uploaded:
            service.cleanup_file(uploaded[0])

    result = await run_mutation(session, action, cleanup)
    if pending_generations:
        queue_file_index(background_tasks, result.id, pending_generations[0])
    return result


@router.get(
    "/pages/{page_id}/files",
    response_model=FileMetadataListResponse,
    summary="List page attachments",
)
async def list_page_files(page_id: UUID, session: DbSession) -> FileMetadataListResponse:
    service = FileService(session)
    files = await service.list_page_files(str(page_id))
    return FileMetadataListResponse(items=[FileMetadataRead.model_validate(item) for item in files])


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


@router.post("/files/{file_id}/index/retry", summary="Retry file content search")
async def retry_file_index(
    file_id: UUID, session: DbSession, background_tasks: BackgroundTasks
) -> dict[str, str]:
    file_metadata = await FileService(session).get_file(str(file_id))
    if file_metadata is None:
        raise NotFoundError("file metadata not found")
    generation = await FileIndexService(session).mark_pending(file_metadata.id)
    await session.commit()
    if generation is None:
        return {"status": "metadata_only"}
    queue_file_index(background_tasks, file_metadata.id, generation)
    return {"status": "pending"}


@router.get("/files/{file_id}/download", summary="Download file")
async def download_file(file_id: UUID, session: DbSession) -> FileResponse:
    service = FileService(session)
    file_metadata = await service.get_file(str(file_id))
    if file_metadata is None:
        raise NotFoundError("file metadata not found")
    path = service.download_path(file_metadata)
    return FileResponse(path, media_type=file_metadata.mime_type, filename=file_metadata.name)


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
