from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.api.dependencies import get_db_session
from goldenson_api.api.knowledge_tasks import queue_page_delete, queue_page_index
from goldenson_api.api.transaction import run_mutation
from goldenson_api.db.models.knowledge import PageKnowledge
from goldenson_api.schemas.page import (
    PageCreate,
    PageCreateRequest,
    PageListResponse,
    PageRead,
    PageUpdate,
)
from goldenson_api.services.errors import NotFoundError
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService

router = APIRouter(tags=["Pages"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


@router.get(
    "/workspaces/{workspace_id}/pages",
    response_model=PageListResponse,
    summary="List pages in a workspace",
)
async def list_pages(
    workspace_id: UUID,
    session: DbSession,
) -> PageListResponse:
    service = PageService(session)
    pages = await service.list_pages(str(workspace_id))
    return PageListResponse(items=[PageRead.model_validate(page) for page in pages])


@router.post(
    "/workspaces/{workspace_id}/pages",
    response_model=PageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create page",
)
async def create_page(
    workspace_id: UUID,
    payload: PageCreateRequest,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> PageRead:
    service = PageService(session)

    async def action() -> PageRead:
        page = await service.create_page(
            PageCreate(
                workspace_id=str(workspace_id),
                title=payload.title,
                parent_page_id=(
                    None if payload.parent_page_id is None else str(payload.parent_page_id)
                ),
                position=payload.position,
            )
        )
        return PageRead.model_validate(page)

    result = await run_mutation(session, action)
    queue_page_index(background_tasks, result.id, result.version)
    return result


@router.get("/pages/{page_id}", response_model=PageRead, summary="Get page")
async def get_page(page_id: UUID, session: DbSession) -> PageRead:
    service = PageService(session)
    page = await service.get_page(str(page_id))
    if page is None:
        raise NotFoundError("page not found")
    return PageRead.model_validate(page)


@router.patch("/pages/{page_id}", response_model=PageRead, summary="Update page")
async def update_page(
    page_id: UUID,
    payload: PageUpdate,
    session: DbSession,
    background_tasks: BackgroundTasks,
) -> PageRead:
    service = PageService(session)
    set_parent = "parent_page_id" in payload.model_fields_set

    async def action() -> PageRead:
        page = await service.update_page(str(page_id), payload, set_parent=set_parent)
        return PageRead.model_validate(page)

    result = await run_mutation(session, action)
    queue_page_index(background_tasks, result.id, result.version)
    return result


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete page")
async def delete_page(page_id: UUID, session: DbSession, background_tasks: BackgroundTasks) -> None:
    service = PageService(session)

    async def action() -> None:
        await service.delete_page(str(page_id))

    await run_mutation(session, action)
    queue_page_delete(background_tasks, str(page_id))


@router.get("/pages/{page_id}/related", summary="List related pages")
async def related_pages(page_id: UUID, session: DbSession) -> dict[str, object]:
    service = KnowledgeService(session)
    related = await service.related(str(page_id))
    pages = PageService(session)
    items = []
    for record, _, reason in related:
        page = await pages.get_page(record.page_id)
        if page is not None:
            items.append({"page_id": page.id, "title": page.title, "reason": reason})
    return {"items": items}


@router.get("/pages/{page_id}/knowledge", summary="Get page knowledge state")
async def page_knowledge(page_id: UUID, session: DbSession) -> dict[str, object]:
    record = await session.scalar(
        select(PageKnowledge).where(PageKnowledge.page_id == str(page_id))
    )
    if record is None:
        return {"status": "pending", "concepts": []}
    return {"status": record.status, "concepts": record.concepts, "indexed_at": record.indexed_at}


@router.post("/pages/{page_id}/knowledge/reindex", summary="Retry page indexing")
async def reindex_page(
    page_id: UUID, session: DbSession, background_tasks: BackgroundTasks
) -> dict[str, str]:
    page = await PageService(session).get_page(str(page_id))
    if page is None:
        raise NotFoundError("page not found")
    await KnowledgeService(session).mark_pending(page.id)
    await session.commit()
    queue_page_index(background_tasks, page.id, page.version)
    return {"status": "pending"}
