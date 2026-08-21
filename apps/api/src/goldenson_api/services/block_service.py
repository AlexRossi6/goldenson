from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.block import Block
from goldenson_api.db.repositories.block_repository import BlockRepository
from goldenson_api.db.repositories.page_repository import PageRepository
from goldenson_api.schemas.block import BlockCreate, BlockUpdate, BlockUpdateContent
from goldenson_api.services.errors import (
    BadRequestError,
    ConcurrencyConflictError,
    NotFoundError,
)


class BlockService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = BlockRepository(session)
        self._page_repository = PageRepository(session)

    async def create_block(self, payload: BlockCreate) -> Block:
        page = await self._page_repository.get_by_id(payload.page_id)
        if page is None:
            raise NotFoundError("page not found")

        return await self._repository.create(
            page_id=payload.page_id,
            block_type=payload.type,
            position=payload.position,
            content=payload.content,
        )

    async def get_block(self, block_id: str) -> Block | None:
        return await self._repository.get_by_id(block_id)

    async def list_blocks(self, page_id: str) -> list[Block]:
        page = await self._page_repository.get_by_id(page_id)
        if page is None:
            raise NotFoundError("page not found")
        return await self._repository.list_for_page(page_id)

    async def update_content(self, block_id: str, payload: BlockUpdateContent) -> Block:
        updated = await self._repository.update_content_with_version(
            block_id,
            content=payload.content,
            expected_version=payload.expected_version,
        )
        if updated is None:
            raise ConcurrencyConflictError("block update rejected due to stale version")
        return updated

    async def update_block(self, block_id: str, payload: BlockUpdate) -> Block:
        block = await self._repository.get_by_id(block_id)
        if block is None:
            raise NotFoundError("block not found")

        if payload.type is None and payload.position is None and payload.content is None:
            raise BadRequestError("no mutable block fields were provided")

        updated = await self._repository.update_with_version(
            block_id,
            expected_version=payload.version,
            block_type=payload.type,
            position=payload.position,
            content=payload.content,
        )
        if updated is None:
            raise ConcurrencyConflictError("block update rejected due to stale version")
        return updated

    async def delete_block(self, block_id: str) -> None:
        block = await self._repository.get_by_id(block_id)
        if block is None:
            raise NotFoundError("block not found")

        deleted = await self._repository.delete_by_id(block_id)
        if not deleted:
            raise NotFoundError("block not found")
