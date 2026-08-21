import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.block import Block
from goldenson_api.db.models.file_metadata import FileMetadata
from goldenson_api.db.models.page import Page
from goldenson_api.db.models.workspace import Workspace
from goldenson_api.scripts.seed import seed


@pytest.mark.asyncio
async def test_seed_is_idempotent(migrated_db_url: str, session: AsyncSession) -> None:
    await seed(migrated_db_url)
    await seed(migrated_db_url)

    workspaces = (await session.execute(select(Workspace))).scalars().all()
    pages = (await session.execute(select(Page))).scalars().all()
    blocks = (await session.execute(select(Block))).scalars().all()
    files = (await session.execute(select(FileMetadata))).scalars().all()

    assert len(workspaces) == 1
    assert len(pages) >= 7
    assert len(blocks) >= 5
    assert len(files) == 3
