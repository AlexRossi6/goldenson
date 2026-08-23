import logging

from fastapi import BackgroundTasks

from goldenson_api.db.session import SessionLocal
from goldenson_api.services.knowledge_service import KnowledgeService


async def index_page(page_id: str, page_version: int | None = None) -> None:
    async with SessionLocal() as session:
        try:
            await KnowledgeService(session).mark_pending(page_id)
            await session.commit()
        except Exception:
            logging.getLogger(__name__).exception(
                "knowledge status update failed for page %s", page_id
            )
            await session.rollback()

    async with SessionLocal() as session:
        try:
            await KnowledgeService(session).index_page(page_id, page_version)
            await session.commit()
        except Exception as exc:
            logging.getLogger(__name__).exception("knowledge indexing failed for page %s", page_id)
            await session.rollback()
            async with SessionLocal() as failure_session:
                try:
                    await KnowledgeService(failure_session).mark_failed(page_id, str(exc))
                    await failure_session.commit()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "knowledge failure status update failed for page %s", page_id
                    )
                    await failure_session.rollback()


async def delete_page_index(page_id: str) -> None:
    async with SessionLocal() as session:
        try:
            await KnowledgeService(session).delete_page(page_id)
            await session.commit()
        except Exception:
            await session.rollback()


def queue_page_index(
    background_tasks: BackgroundTasks, page_id: str, page_version: int | None = None
) -> None:
    background_tasks.add_task(index_page, page_id, page_version)


def queue_page_delete(background_tasks: BackgroundTasks, page_id: str) -> None:
    background_tasks.add_task(delete_page_index, page_id)
