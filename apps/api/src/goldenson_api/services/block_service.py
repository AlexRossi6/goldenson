from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.block import Block
from goldenson_api.db.repositories.block_repository import BlockRepository
from goldenson_api.schemas.block import BlockCreate, BlockUpdateContent
from goldenson_api.services.errors import ConcurrencyConflictError


class BlockService:
    def __init__(self, session: AsyncSession) -> None:
        self._repository = BlockRepository(session)

    async def create_block(self, payload: BlockCreate) -> Block:
        return await self._repository.create(
            page_id=payload.page_id,
            block_type=payload.type,
            position=payload.position,
            content=payload.content,
        )

    async def list_blocks(self, page_id: str) -> list[Block]:
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
