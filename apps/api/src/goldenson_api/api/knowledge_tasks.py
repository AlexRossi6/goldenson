import asyncio
import logging

from fastapi import BackgroundTasks

from goldenson_api.core.config import get_settings
from goldenson_api.db.models.page import Page
from goldenson_api.db.session import SessionLocal
from goldenson_api.services.file_index_service import FileIndexService
from goldenson_api.services.knowledge_service import KnowledgeService


async def index_page(
    page_id: str,
    page_version: int | None = None,
    generation: int | None = None,
) -> None:
    async with SessionLocal() as session:
        try:
            page = await session.get(Page, page_id)
            if page is None or (page_version is not None and page.version != page_version):
                return
            service = KnowledgeService(session)
            if generation is None:
                generation = await service.mark_pending(page_id)
            if generation is None or not await service.mark_indexing(page_id, generation):
                return
            await session.commit()
        except Exception:
            logging.getLogger(__name__).exception(
                "knowledge status update failed for page %s", page_id
            )
            await session.rollback()
            return

    async with SessionLocal() as session:
        try:
            async with asyncio.timeout(get_settings().knowledge_index_timeout_seconds):
                await KnowledgeService(session).index_page(
                    page_id, page_version, expected_generation=generation
                )
            await session.commit()
        except Exception:
            logging.getLogger(__name__).exception("knowledge indexing failed for page %s", page_id)
            await session.rollback()
            async with SessionLocal() as failure_session:
                try:
                    await KnowledgeService(failure_session).mark_failed(page_id, generation)
                    await failure_session.commit()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "knowledge failure status update failed for page %s", page_id
                    )
                    await failure_session.rollback()


async def index_file(file_id: str, generation: int) -> None:
    async with SessionLocal() as session:
        try:
            if not await FileIndexService(session).mark_indexing(file_id, generation):
                return
            await session.commit()
        except Exception:
            logging.getLogger(__name__).exception(
                "file index status update failed for file %s", file_id
            )
            await session.rollback()
            return

    async with SessionLocal() as session:
        try:
            async with asyncio.timeout(get_settings().knowledge_index_timeout_seconds):
                await FileIndexService(session).index_file(file_id, generation)
            await session.commit()
        except Exception:
            logging.getLogger(__name__).exception("file indexing failed for file %s", file_id)
            await session.rollback()
            async with SessionLocal() as failure_session:
                try:
                    await FileIndexService(failure_session).mark_failed(file_id, generation)
                    await failure_session.commit()
                except Exception:
                    logging.getLogger(__name__).exception(
                        "file failure status update failed for file %s", file_id
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
    background_tasks: BackgroundTasks,
    page_id: str,
    page_version: int | None = None,
    generation: int | None = None,
) -> None:
    background_tasks.add_task(index_page, page_id, page_version, generation)


def queue_file_index(background_tasks: BackgroundTasks, file_id: str, generation: int) -> None:
    background_tasks.add_task(index_file, file_id, generation)


def queue_page_delete(background_tasks: BackgroundTasks, page_id: str) -> None:
    background_tasks.add_task(delete_page_index, page_id)
