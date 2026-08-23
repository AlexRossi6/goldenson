from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from goldenson_api.core.config import get_settings


def create_engine_and_sessionmaker(
    database_url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(database_url, future=True)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        dbapi_connection.run_async(lambda connection: connection.execute("PRAGMA foreign_keys=ON"))  # type: ignore[attr-defined]

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


settings = get_settings()
engine, SessionLocal = create_engine_and_sessionmaker(settings.database_url)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
