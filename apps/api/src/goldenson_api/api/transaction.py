from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession


async def run_mutation[T](session: AsyncSession, action: Callable[[], Awaitable[T]]) -> T:
    try:
        result = await action()
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        raise
