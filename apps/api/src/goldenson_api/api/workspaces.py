from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.transaction import run_mutation
from goldenson_api.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceListResponse,
    WorkspaceRead,
)
from goldenson_api.services.errors import NotFoundError
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
