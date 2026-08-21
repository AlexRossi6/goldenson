from datetime import UTC, datetime
from typing import cast

from sqlalchemy import Result, delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.block import Block


def _utc_now() -> datetime:
    return datetime.now(UTC)


class BlockRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        page_id: str,
        block_type: str,
        position: int,
        content: dict[str, object],
    ) -> Block:
        block = Block(page_id=page_id, type=block_type, position=position, content=content)
        self._session.add(block)
        await self._session.flush()
        return block

    async def get_by_id(self, block_id: str) -> Block | None:
        return await self._session.get(Block, block_id)

    async def list_for_page(self, page_id: str) -> list[Block]:
        stmt = select(Block).where(Block.page_id == page_id).order_by(Block.position.asc())
        result: Result[tuple[Block]] = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_content_with_version(
        self,
        block_id: str,
        *,
        content: dict[str, object],
        expected_version: int,
    ) -> Block | None:
        stmt = (
            update(Block)
            .where(Block.id == block_id, Block.version == expected_version)
            .values(content=content, version=expected_version + 1, updated_at=_utc_now())
        )
        result = cast(CursorResult[tuple[object]], await self._session.execute(stmt))
        updated_rows = result.rowcount or 0
        if updated_rows != 1:
            return None

        await self._session.flush()
        return await self.get_by_id(block_id)

    async def update_with_version(
        self,
        block_id: str,
        *,
        expected_version: int,
        block_type: str | None,
        position: int | None,
        content: dict[str, object] | None,
    ) -> Block | None:
        values: dict[str, object] = {
            "version": expected_version + 1,
            "updated_at": _utc_now(),
        }
        if block_type is not None:
            values["type"] = block_type
        if position is not None:
            values["position"] = position
        if content is not None:
            values["content"] = content

        stmt = (
            update(Block)
            .where(Block.id == block_id, Block.version == expected_version)
            .values(**values)
        )
        result = cast(CursorResult[tuple[object]], await self._session.execute(stmt))
        if (result.rowcount or 0) != 1:
            return None

        await self._session.flush()
        return await self.get_by_id(block_id)

    async def delete_by_id(self, block_id: str) -> bool:
        result = cast(
            CursorResult[tuple[object]],
            await self._session.execute(delete(Block).where(Block.id == block_id)),
        )
        return bool((result.rowcount or 0) == 1)
