import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_create_root_and_nested_pages(session: AsyncSession) -> None:
    workspace_service = WorkspaceService(session)
    page_service = PageService(session)

    workspace = await workspace_service.create_workspace(WorkspaceCreate(name="Pages Workspace"))
    root = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=None, title="Root", position=0)
    )
    child = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=root.id, title="Child", position=0)
    )
    await session.commit()

    fetched_root = await page_service.get_page(root.id)
    fetched_child = await page_service.get_page(child.id)

    assert fetched_root is not None
    assert fetched_child is not None
    assert fetched_child.parent_page_id == fetched_root.id


@pytest.mark.asyncio
async def test_sibling_ordering_and_parent_relationships(session: AsyncSession) -> None:
    workspace_service = WorkspaceService(session)
    page_service = PageService(session)

    workspace = await workspace_service.create_workspace(WorkspaceCreate(name="Ordering Workspace"))
    root = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=None, title="Root", position=0)
    )
    _ = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=root.id, title="Second", position=2)
    )
    _ = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=root.id, title="First", position=1)
    )
    await session.commit()

    children = await page_service.list_children(workspace.id, root.id)

    assert [child.title for child in children] == ["First", "Second"]
    assert all(child.parent_page_id == root.id for child in children)
