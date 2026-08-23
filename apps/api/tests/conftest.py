from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alembic import command
from goldenson_api.api import knowledge_tasks
from goldenson_api.api.dependencies import get_db_session
from goldenson_api.core.config import get_settings
from goldenson_api.db.session import create_engine_and_sessionmaker
from goldenson_api.main import create_app


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
    engine, factory = create_engine_and_sessionmaker(migrated_db_url)

    yield factory

    await engine.dispose()


@pytest.fixture()
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as current_session:
        yield current_session


@pytest.fixture()
def api_client(
    migrated_db_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("GOLDENSON_STORAGE_ROOT", str(tmp_path / "files"))
    get_settings.cache_clear()
    engine, factory = create_engine_and_sessionmaker(migrated_db_url)
    monkeypatch.setattr(knowledge_tasks, "SessionLocal", factory)

    app = create_app()

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
    get_settings.cache_clear()
