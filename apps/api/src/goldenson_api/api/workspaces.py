from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.knowledge_tasks import queue_file_index, queue_page_index
from goldenson_api.api.transaction import run_mutation
from goldenson_api.retrieval.service import RetrievalResult, WorkspaceRetrievalService
from goldenson_api.schemas.index_health import (
    RetryFailedIndexingResponse,
    WorkspaceIndexHealth,
)
from goldenson_api.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceRead,
)
from goldenson_api.services.errors import NotFoundError
from goldenson_api.services.file_index_service import FileIndexService
from goldenson_api.services.index_health_service import IndexHealthService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("", response_model=WorkspaceListResponse, summary="List workspaces")
async def list_workspaces(session: DbSession) -> WorkspaceListResponse:
    service = WorkspaceService(session)
    items = await service.list_workspaces()
    return WorkspaceListResponse(items=[WorkspaceRead.model_validate(item) for item in items])


@router.post(
    "",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace",
)
async def create_workspace(
    payload: WorkspaceCreate,
    session: DbSession,
) -> WorkspaceRead:
    service = WorkspaceService(session)

    async def action() -> WorkspaceRead:
        workspace = await service.create_workspace(payload)
        return WorkspaceRead.model_validate(workspace)

    return await run_mutation(session, action)


@router.get("/{workspace_id}", response_model=WorkspaceRead, summary="Get workspace")
async def get_workspace(
    workspace_id: UUID,
    session: DbSession,
) -> WorkspaceRead:
    service = WorkspaceService(session)
    workspace = await service.get_workspace(str(workspace_id))
    if workspace is None:
        raise NotFoundError("workspace not found")
    return WorkspaceRead.model_validate(workspace)


@router.get(
    "/{workspace_id}/search",
    response_model=RetrievalResult,
    summary="Search workspace knowledge",
)
async def search_workspace(
    workspace_id: UUID,
    session: DbSession,
    query: Annotated[str, Query(min_length=1, max_length=1000)],
    limit: Annotated[int, Query(ge=1, le=10)] = 8,
) -> RetrievalResult:
    workspace = await WorkspaceService(session).get_workspace(str(workspace_id))
    if workspace is None:
        raise NotFoundError("workspace not found")
    return await WorkspaceRetrievalService(session).search(str(workspace_id), query, limit)


@router.get(
    "/{workspace_id}/index-health",
    response_model=WorkspaceIndexHealth,
    summary="Get workspace index health",
)
async def workspace_index_health(workspace_id: UUID, session: DbSession) -> WorkspaceIndexHealth:
    workspace = await WorkspaceService(session).get_workspace(str(workspace_id))
    if workspace is None:
        raise NotFoundError("workspace not found")
    return await IndexHealthService(session).workspace_health(workspace.id)


@router.post(
    "/{workspace_id}/index/retry-failed",
    response_model=RetryFailedIndexingResponse,
    summary="Retry failed workspace indexing",
)
async def retry_failed_workspace_indexing(
    workspace_id: UUID,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> RetryFailedIndexingResponse:
    workspace = await WorkspaceService(session).get_workspace(str(workspace_id))
    if workspace is None:
        raise NotFoundError("workspace not found")
    health = IndexHealthService(session)
    page_service = PageService(session)
    page_index = KnowledgeService(session)
    file_index = FileIndexService(session)
    queued_pages: list[tuple[str, int, int]] = []
    queued_files: list[tuple[str, int]] = []
    for page_id in await health.failed_page_ids(workspace.id):
        page = await page_service.get_page(page_id)
        generation = await page_index.mark_pending(page_id)
        if page is not None and generation is not None:
            queued_pages.append((page.id, page.version, generation))
    for file_id in await health.failed_file_ids(workspace.id):
        generation = await file_index.mark_pending(file_id)
        if generation is not None:
            queued_files.append((file_id, generation))
    await session.commit()
    for page_id, page_version, generation in queued_pages:
        queue_page_index(background_tasks, page_id, page_version, generation)
    for file_id, generation in queued_files:
        queue_file_index(background_tasks, file_id, generation)
    return RetryFailedIndexingResponse(queued=len(queued_pages) + len(queued_files))
