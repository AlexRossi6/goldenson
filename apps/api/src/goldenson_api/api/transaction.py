from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession


async def run_mutation[T](
    session: AsyncSession,
    action: Callable[[], Awaitable[T]],
    on_failure: Callable[[], Awaitable[None]] | None = None,
) -> T:
    try:
        result = await action()
        await session.commit()
        return result
    except Exception:
        await session.rollback()
        if on_failure is not None:
            await on_failure()
        raise
