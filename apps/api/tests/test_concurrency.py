import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from goldenson_api.schemas.page import PageCreate, PageUpdateTitle
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.errors import ConcurrencyConflictError
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_page_optimistic_concurrency(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as setup_session:
        workspace_service = WorkspaceService(setup_session)
        page_service = PageService(setup_session)

        workspace = await workspace_service.create_workspace(
            WorkspaceCreate(name="Concurrency Workspace")
        )
        page = await page_service.create_page(
            PageCreate(workspace_id=workspace.id, parent_page_id=None, title="Draft", position=0)
        )
        await setup_session.commit()
        page_id = page.id

    async with session_factory() as first_reader, session_factory() as second_reader:
        first_page_service = PageService(first_reader)
        second_page_service = PageService(second_reader)

        first_snapshot = await first_page_service.get_page(page_id)
        second_snapshot = await second_page_service.get_page(page_id)

        assert first_snapshot is not None
        assert second_snapshot is not None
        assert first_snapshot.version == second_snapshot.version
        initial_version = first_snapshot.version

        updated = await first_page_service.update_title(
            page_id,
            PageUpdateTitle(title="Updated by first", expected_version=initial_version),
        )
        await first_reader.commit()

        with pytest.raises(ConcurrencyConflictError):
            await second_page_service.update_title(
                page_id,
                PageUpdateTitle(
                    title="Stale second write", expected_version=second_snapshot.version
                ),
            )
        await second_reader.rollback()

        assert updated.version == initial_version + 1

    async with session_factory() as verify_session:
        page_service = PageService(verify_session)
        current = await page_service.get_page(page_id)

        assert current is not None
        assert current.title == "Updated by first"
