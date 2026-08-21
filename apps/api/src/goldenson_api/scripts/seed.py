from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.core.config import get_settings
from goldenson_api.db.repositories.block_repository import BlockRepository
from goldenson_api.db.session import create_engine_and_sessionmaker
from goldenson_api.schemas.block import BlockCreate
from goldenson_api.schemas.file_metadata import FileMetadataCreate
from goldenson_api.schemas.page import PageCreate
from goldenson_api.schemas.workspace import WorkspaceCreate
from goldenson_api.services.block_service import BlockService
from goldenson_api.services.file_service import FileService
from goldenson_api.services.page_service import PageService
from goldenson_api.services.workspace_service import WorkspaceService

WORKSPACE_NAME = "Research Lab Workspace"


async def _ensure_page(
    session: AsyncSession,
    workspace_id: str,
    *,
    title: str,
    position: int,
    parent_page_id: str | None,
) -> str:
    page_service = PageService(session)
    existing = await page_service.get_by_title_and_parent(workspace_id, title, parent_page_id)
    if existing is not None:
        return existing.id

    created = await page_service.create_page(
        PageCreate(
            workspace_id=workspace_id,
            parent_page_id=parent_page_id,
            title=title,
            position=position,
        )
    )
    return created.id


async def _seed_blocks(session: AsyncSession, page_id: str) -> None:
    block_repository = BlockRepository(session)
    existing_blocks = await block_repository.list_for_page(page_id)
    if existing_blocks:
        return

    block_service = BlockService(session)
    payloads = [
        BlockCreate(
            page_id=page_id,
            type="heading",
            position=0,
            content={"text": "AI Research Weekly", "level": 2},
        ),
        BlockCreate(
            page_id=page_id,
            type="paragraph",
            position=1,
            content={
                "text": (
                    "Review emerging open-source model releases and evaluate "
                    "their fit for local inference workflows."
                )
            },
        ),
        BlockCreate(
            page_id=page_id,
            type="todo",
            position=2,
            content={"text": "Run benchmark on quantized 8B model", "checked": False},
        ),
        BlockCreate(
            page_id=page_id,
            type="code",
            position=3,
            content={"language": "python", "code": "print('embedding drift check')"},
        ),
        BlockCreate(
            page_id=page_id,
            type="callout",
            position=4,
            content={"emoji": "note", "text": "Track model license constraints early."},
        ),
    ]

    for payload in payloads:
        await block_service.create_block(payload)


async def seed(database_url: str | None = None) -> None:
    settings = get_settings()
    target_database_url = database_url or settings.database_url
    engine, session_factory = create_engine_and_sessionmaker(target_database_url)

    async with session_factory() as session:
        workspace_service = WorkspaceService(session)
        workspace = await workspace_service.get_workspace_by_name(WORKSPACE_NAME)
        if workspace is None:
            workspace = await workspace_service.create_workspace(
                WorkspaceCreate(name=WORKSPACE_NAME)
            )
            await session.flush()

        research_page_id = await _ensure_page(
            session,
            workspace.id,
            title="AI Research",
            position=0,
            parent_page_id=None,
        )
        projects_page_id = await _ensure_page(
            session,
            workspace.id,
            title="Projects",
            position=1,
            parent_page_id=None,
        )
        ideas_page_id = await _ensure_page(
            session,
            workspace.id,
            title="Ideas",
            position=2,
            parent_page_id=None,
        )

        weekly_notes_page_id = await _ensure_page(
            session,
            workspace.id,
            title="Weekly Notes",
            position=0,
            parent_page_id=research_page_id,
        )
        _ = await _ensure_page(
            session,
            workspace.id,
            title="Model Evaluations",
            position=1,
            parent_page_id=research_page_id,
        )
        _ = await _ensure_page(
            session,
            workspace.id,
            title="Knowledge Assistant MVP",
            position=0,
            parent_page_id=projects_page_id,
        )
        _ = await _ensure_page(
            session,
            workspace.id,
            title="Future Product Concepts",
            position=0,
            parent_page_id=ideas_page_id,
        )

        await _seed_blocks(session, weekly_notes_page_id)

        file_service = FileService(session)
        file_examples = [
            FileMetadataCreate(
                workspace_id=workspace.id,
                page_id=weekly_notes_page_id,
                name="benchmark-results.csv",
                storage_key="seed/benchmark-results.csv",
                mime_type="text/csv",
                size=18432,
            ),
            FileMetadataCreate(
                workspace_id=workspace.id,
                page_id=projects_page_id,
                name="architecture-sketch.png",
                storage_key="seed/architecture-sketch.png",
                mime_type="image/png",
                size=95321,
            ),
            FileMetadataCreate(
                workspace_id=workspace.id,
                page_id=None,
                name="roadmap-notes.md",
                storage_key="seed/roadmap-notes.md",
                mime_type="text/markdown",
                size=2409,
            ),
        ]

        for file_payload in file_examples:
            existing = await file_service.get_by_storage_key(file_payload.storage_key)
            if existing is None:
                await file_service.create_file(file_payload)

        await session.commit()

    await engine.dispose()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
