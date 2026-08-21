from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command


@pytest.fixture()
def db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "test.db"
    return f"sqlite+aiosqlite:///{db_file}"


@pytest.fixture()
def migrated_db_url(db_url: str) -> str:
    project_root = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(project_root / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(project_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", db_url)

    command.upgrade(alembic_config, "head")
    return db_url


@pytest.fixture()
async def session_factory(
    migrated_db_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(migrated_db_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    yield factory

    await engine.dispose()


@pytest.fixture()
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as current_session:
        yield current_session
