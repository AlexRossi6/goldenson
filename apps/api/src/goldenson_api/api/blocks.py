from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.knowledge_tasks import queue_page_index
from goldenson_api.api.transaction import run_mutation
from goldenson_api.schemas.block import (
    BlockCreate,
    BlockCreateRequest,
    BlockListResponse,
    BlockRead,
    BlockReorderRequest,
    BlockUpdate,
)
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.page_service import PageService

router = APIRouter(tags=["Blocks"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get("/pages/{page_id}/blocks", response_model=BlockListResponse, summary="List blocks")
async def list_blocks(
    page_id: UUID,
    session: DbSession,
) -> BlockListResponse:
    service = BlockService(session)
    blocks = await service.list_blocks(str(page_id))
    return BlockListResponse(items=[BlockRead.model_validate(block) for block in blocks])


@router.post(
    "/pages/{page_id}/blocks",
    response_model=BlockRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create block",
)
async def create_block(
    page_id: UUID,
    payload: BlockCreateRequest,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> BlockRead:
    service = BlockService(session)

    async def action() -> BlockRead:
        block = await service.create_block(
            BlockCreate(
                page_id=str(page_id),
                type=payload.type,
                position=payload.position,
                content=payload.content,
            )
        )
        return BlockRead.model_validate(block)

    result = await run_mutation(session, action)
    page = await PageService(session).get_page(result.page_id)
    queue_page_index(background_tasks, result.page_id, None if page is None else page.version)
    return result


@router.patch("/blocks/{block_id}", response_model=BlockRead, summary="Update block")
async def update_block(
    block_id: UUID,
    payload: BlockUpdate,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> BlockRead:
    service = BlockService(session)

    async def action() -> BlockRead:
        block = await service.update_block(str(block_id), payload)
        return BlockRead.model_validate(block)

    result = await run_mutation(session, action)
    page = await PageService(session).get_page(result.page_id)
    queue_page_index(background_tasks, result.page_id, None if page is None else page.version)
    return result


@router.post(
    "/pages/{page_id}/blocks/reorder",
    response_model=BlockListResponse,
    summary="Reorder blocks",
)
async def reorder_blocks(
    page_id: UUID,
    payload: BlockReorderRequest,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> BlockListResponse:
    service = BlockService(session)

    async def action() -> BlockListResponse:
        blocks = await service.reorder_blocks(str(page_id), payload.block_ids, payload.versions)
        return BlockListResponse(items=[BlockRead.model_validate(block) for block in blocks])

    result = await run_mutation(session, action)
    page = await PageService(session).get_page(str(page_id))
    queue_page_index(background_tasks, str(page_id), None if page is None else page.version)
    return result


@router.delete(
    "/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete block",
)
async def delete_block(
    block_id: UUID,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> None:
    service = BlockService(session)
    block = await service.get_block(str(block_id))
    page_id = None if block is None else block.page_id

    async def action() -> None:
        await service.delete_block(str(block_id))

    await run_mutation(session, action)
    if page_id is not None:
        page = await PageService(session).get_page(page_id)
        queue_page_index(background_tasks, page_id, None if page is None else page.version)
