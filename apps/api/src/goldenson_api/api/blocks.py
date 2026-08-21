from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.transaction import run_mutation
from goldenson_api.schemas.block import (
    BlockCreate,
    BlockCreateRequest,
    BlockListResponse,
    BlockRead,
    BlockUpdate,
)
from goldenson_api.services.block_service import BlockService

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

    return await run_mutation(session, action)


@router.patch("/blocks/{block_id}", response_model=BlockRead, summary="Update block")
async def update_block(
    block_id: UUID,
    payload: BlockUpdate,
    session: DbSession,
) -> BlockRead:
    service = BlockService(session)

    async def action() -> BlockRead:
        block = await service.update_block(str(block_id), payload)
        return BlockRead.model_validate(block)

    return await run_mutation(session, action)


@router.delete(
    "/blocks/{block_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete block",
)
async def delete_block(block_id: UUID, session: DbSession) -> None:
    service = BlockService(session)

    async def action() -> None:
        await service.delete_block(str(block_id))

    await run_mutation(session, action)
