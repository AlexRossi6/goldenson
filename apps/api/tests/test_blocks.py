import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.schemas.block import BlockCreate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.block_service import BlockService
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
