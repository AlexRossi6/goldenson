import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.block import BlockCreate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.errors import BadRequestError, ConcurrencyConflictError
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService


@pytest.mark.asyncio
async def test_create_blocks_ordering_and_json_content(session: AsyncSession) -> None:
    workspace_service = WorkspaceService(session)
    page_service = PageService(session)
    block_service = BlockService(session)

    workspace = await workspace_service.create_workspace(WorkspaceCreate(name="Blocks Workspace"))
    page = await page_service.create_page(
        PageCreate(workspace_id=workspace.id, parent_page_id=None, title="Page", position=0)
    )

    await block_service.create_block(
        BlockCreate(
            page_id=page.id, type="todo", position=1, content={"text": "Later", "checked": False}
        )
    )
    await block_service.create_block(
        BlockCreate(page_id=page.id, type="paragraph", position=0, content={"text": "First"})
    )
    await session.commit()

    blocks = await block_service.list_blocks(page.id)

    assert [block.position for block in blocks] == [0, 1]
    assert blocks[0].content == {"text": "First"}
    assert blocks[1].content == {"text": "Later", "checked": False}


@pytest.mark.asyncio
async def test_create_block_after_delete_uses_next_available_position(
    session: AsyncSession,
) -> None:
    workspace = await WorkspaceService(session).create_workspace(
        WorkspaceCreate(name="Block Position Workspace")
    )
    page = await PageService(session).create_page(
        PageCreate(workspace_id=workspace.id, title="Page", position=0)
    )
    block_service = BlockService(session)
    first = await block_service.create_block(
        BlockCreate(page_id=page.id, type="paragraph", position=0, content={"text": "First"})
    )
    second = await block_service.create_block(
        BlockCreate(page_id=page.id, type="paragraph", position=1, content={"text": "Second"})
    )
    await session.commit()

    await block_service.delete_block(first.id)
    created = await block_service.create_block(
        BlockCreate(page_id=page.id, type="heading", position=1, content={"text": "Third"})
    )
    await session.commit()

    blocks = await block_service.list_blocks(page.id)
    assert [block.id for block in blocks] == [second.id, created.id]
    assert [block.position for block in blocks] == [1, 2]


@pytest.mark.asyncio
async def test_reorder_blocks_preserves_identity_content_and_order_after_reload(
    session: AsyncSession,
) -> None:
    workspace = await WorkspaceService(session).create_workspace(
        WorkspaceCreate(name="Reorder Workspace")
    )
    page = await PageService(session).create_page(
        PageCreate(workspace_id=workspace.id, title="Page", position=0)
    )
    block_service = BlockService(session)
    block_fixtures: list[tuple[str, dict[str, object]]] = [
        ("paragraph", {"text": "First"}),
        ("heading", {"text": "Section"}),
        ("todo", {"title": "Tasks", "items": []}),
    ]
    created = [
        await block_service.create_block(
            BlockCreate(page_id=page.id, type=block_type, position=index, content=content)
        )
        for index, (block_type, content) in enumerate(block_fixtures)
    ]
    await session.commit()
    versions = {block.id: block.version for block in created}

    reordered = await block_service.reorder_blocks(
        page.id, [created[2].id, created[0].id, created[1].id], versions
    )
    await session.commit()

    assert [block.id for block in reordered] == [created[2].id, created[0].id, created[1].id]
    assert [block.position for block in reordered] == [0, 1, 2]
    assert [block.content for block in reordered] == [
        {"title": "Tasks", "items": []},
        {"text": "First"},
        {"text": "Section"},
    ]
    reloaded = await BlockService(session).list_blocks(page.id)
    assert [block.id for block in reloaded] == [created[2].id, created[0].id, created[1].id]


@pytest.mark.asyncio
async def test_reorder_blocks_rejects_incomplete_or_stale_requests(session: AsyncSession) -> None:
    workspace = await WorkspaceService(session).create_workspace(
        WorkspaceCreate(name="Reorder Validation")
    )
    page = await PageService(session).create_page(
        PageCreate(workspace_id=workspace.id, title="Page", position=0)
    )
    block_service = BlockService(session)
    block = await block_service.create_block(
        BlockCreate(page_id=page.id, type="paragraph", position=0, content={"text": "Text"})
    )
    await session.commit()

    with pytest.raises(BadRequestError):
        await block_service.reorder_blocks(page.id, [], {block.id: block.version})
    with pytest.raises(ConcurrencyConflictError):
        await block_service.reorder_blocks(page.id, [block.id], {block.id: block.version + 1})
