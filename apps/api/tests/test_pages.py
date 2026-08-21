import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.block import BlockCreate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.block_service import BlockService
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


@pytest.mark.asyncio
async def test_delete_page_removes_nested_pages_and_blocks(session: AsyncSession) -> None:
    workspace = await WorkspaceService(session).create_workspace(WorkspaceCreate(name="Cascade"))
    pages = PageService(session)
    blocks = BlockService(session)
    root = await pages.create_page(PageCreate(workspace_id=workspace.id, title="Root", position=0))
    child = await pages.create_page(
        PageCreate(workspace_id=workspace.id, title="Child", position=0, parent_page_id=root.id)
    )
    grandchild = await pages.create_page(
        PageCreate(
            workspace_id=workspace.id,
            title="Grandchild",
            position=0,
            parent_page_id=child.id,
        )
    )
    unrelated = await pages.create_page(
        PageCreate(workspace_id=workspace.id, title="Unrelated", position=1)
    )
    block_ids: list[str] = []
    for page in (root, child, grandchild):
        block = await blocks.create_block(
            BlockCreate(
                page_id=page.id,
                type="paragraph",
                position=0,
                content={"text": page.title},
            )
        )
        block_ids.append(block.id)
    await session.commit()

    await pages.delete_page(root.id)
    await session.commit()

    assert await pages.get_page(root.id) is None
    assert await pages.get_page(child.id) is None
    assert await pages.get_page(grandchild.id) is None
    for block_id in block_ids:
        assert await blocks.get_block(block_id) is None
    assert await pages.get_page(unrelated.id) is not None


@pytest.mark.asyncio
async def test_delete_page_rolls_back_with_outer_transaction_failure(session: AsyncSession) -> None:
    workspace = await WorkspaceService(session).create_workspace(WorkspaceCreate(name="Rollback"))
    pages = PageService(session)
    root = await pages.create_page(PageCreate(workspace_id=workspace.id, title="Root", position=0))
    child = await pages.create_page(
        PageCreate(workspace_id=workspace.id, title="Child", position=0, parent_page_id=root.id)
    )
    root_id = root.id
    child_id = child.id
    await session.commit()

    await pages.delete_page(root_id)
    await session.rollback()

    assert await pages.get_page(root_id) is not None
    assert await pages.get_page(child_id) is not None
