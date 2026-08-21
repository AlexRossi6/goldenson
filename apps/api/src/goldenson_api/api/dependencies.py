from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.session import get_session


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session
