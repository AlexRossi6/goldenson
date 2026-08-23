import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from goldenson_api.api import knowledge_tasks
from goldenson_api.core.config import get_settings
from goldenson_api.db.models.knowledge import PageKnowledge
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


async def test_page_index_timeout_reaches_terminal_failed_state(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with session_factory() as session:
        workspace = await WorkspaceService(session).create_workspace(
            WorkspaceCreate(name="Timeout")
        )
        page = await PageService(session).create_page(
            PageCreate(workspace_id=workspace.id, title="Slow page", position=0)
        )
        generation = await KnowledgeService(session).mark_pending(page.id)
        assert generation is not None
        page_id = page.id
        page_version = page.version
        await session.commit()

    async def hang(*_args: object, **_kwargs: object) -> PageKnowledge:
        await asyncio.sleep(1)
        raise AssertionError("timeout did not stop indexing")

    monkeypatch.setattr(knowledge_tasks, "SessionLocal", session_factory)
    monkeypatch.setattr(KnowledgeService, "index_page", hang)
    monkeypatch.setattr(get_settings(), "knowledge_index_timeout_seconds", 0.001)

    await knowledge_tasks.index_page(page_id, page_version, generation)

    async with session_factory() as session:
        record = await session.scalar(select(PageKnowledge).where(PageKnowledge.page_id == page_id))
        assert record is not None
        assert record.status == "failed"
        assert record.error == "Content indexing could not be completed."
