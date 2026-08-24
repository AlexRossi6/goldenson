from __future__ import annotations

import hashlib
import logging
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar, cast

import httpx
import sqlite_vec  # type: ignore[import-untyped]
from aiosqlite import Connection as AioConnection
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.core.config import get_settings
from goldenson_api.db.models.block import Block
from goldenson_api.db.models.knowledge import PageKnowledge
from goldenson_api.db.models.knowledge_chunk import KnowledgeChunk
from goldenson_api.db.models.page import Page
from goldenson_api.inference.embedding import EmbeddingProvider, OllamaEmbeddingProvider
from goldenson_api.services.block_service import BlockService

ResultT = TypeVar("ResultT")
_MAX_CHUNK_LENGTH = 1200
_CHUNK_OVERLAP = 150
_INDEX_FAILURE_MESSAGE = "Content indexing could not be completed."
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkSpec:
    key: str
    index: int
    source_type: str
    block_id: str | None
    title: str
    text: str


def _block_text(content: dict[str, object]) -> str:
    parts: list[str] = []
    for key in ("title", "text", "code"):
        value = content.get(key)
        if isinstance(value, str):
            parts.append(value)
    items = content.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
    return "\n".join(parts).strip()


def _split_text(text: str) -> list[str]:
    if len(text) <= _MAX_CHUNK_LENGTH:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _MAX_CHUNK_LENGTH, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + _MAX_CHUNK_LENGTH // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - _CHUNK_OVERLAP, start + 1)
    return chunks


def _chunk_specs(page: Page, blocks: Sequence[Block]) -> list[ChunkSpec]:
    specs = [ChunkSpec("page:0", 0, "page", None, page.title, page.title)]
    for block in blocks:
        block_id = block.id
        block_text = _block_text(getattr(block, "content", {}))
        for index, text in enumerate(_split_text(block_text)):
            specs.append(
                ChunkSpec(
                    f"block:{block_id}:{index}",
                    index,
                    "block",
                    block_id,
                    page.title,
                    text,
                )
            )
    return specs


class KnowledgeService:
    _VECTOR_TABLE = "vec_knowledge_chunks"

    def __init__(self, session: AsyncSession, provider: EmbeddingProvider | None = None) -> None:
        self._session = session
        if provider is None:
            settings = get_settings()
            provider = OllamaEmbeddingProvider(
                settings.ollama_base_url,
                settings.embedding_model,
                settings.embedding_provider_version,
            )
        self._embeddings = provider
        self._blocks = BlockService(session)

    async def mark_pending(self, page_id: str) -> int | None:
        record = await self._session.scalar(
            select(PageKnowledge).where(PageKnowledge.page_id == page_id)
        )
        if record is None:
            page = await self._session.get(Page, page_id)
            if page is None:
                return None
            record = PageKnowledge(
                page_id=page.id,
                workspace_id=page.workspace_id,
                content_hash="",
                embedding_model=self._embeddings.model or "unconfigured",
                embedding_version=self._embeddings.version,
                embedding_dimensions=0,
                vector=[],
                concepts=[],
                status="pending",
                generation=1,
            )
            self._session.add(record)
        else:
            record.status = "pending"
            record.error = None
            record.generation += 1
        await self._session.flush()
        return record.generation

    async def mark_indexing(self, page_id: str, expected_generation: int) -> bool:
        record = await self._session.scalar(
            select(PageKnowledge).where(PageKnowledge.page_id == page_id)
        )
        if record is None or record.generation != expected_generation:
            return False
        record.status = "indexing"
        record.error = None
        await self._session.flush()
        return True

    async def mark_failed(self, page_id: str, expected_generation: int | None = None) -> None:
        record = await self._session.scalar(
            select(PageKnowledge).where(PageKnowledge.page_id == page_id)
        )
        if record is not None and (
            expected_generation is None or record.generation == expected_generation
        ):
            record.status = "failed"
            record.error = _INDEX_FAILURE_MESSAGE
            await self._session.flush()

    async def _run_sqlite(self, callback: Callable[[sqlite3.Connection], ResultT]) -> ResultT:
        connection = await self._session.connection()
        raw = await connection.get_raw_connection()
        driver = cast(AioConnection, raw.driver_connection)

        def load_extension(raw_connection: sqlite3.Connection) -> ResultT:
            raw_connection.enable_load_extension(True)
            try:
                sqlite_vec.load(raw_connection)
            finally:
                raw_connection.enable_load_extension(False)
            return callback(raw_connection)

        return cast(ResultT, await driver._execute(load_extension, driver._conn))  # type: ignore[no-untyped-call]

    async def _ensure_vector_table(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("embedding provider returned no dimensions")

        def configure(raw_connection: sqlite3.Connection) -> None:
            current = raw_connection.execute(
                "SELECT embedding_model, embedding_version, embedding_dimensions "
                "FROM knowledge_index_config WHERE id = 1"
            ).fetchone()
            configuration = (self._embeddings.model or "unconfigured", self._embeddings.version)
            if current is not None and (*configuration, dimensions) != tuple(current):
                raw_connection.execute(f"DROP TABLE IF EXISTS {self._VECTOR_TABLE}")
            raw_connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {self._VECTOR_TABLE} USING "
                f"vec0(embedding float[{dimensions}], chunk_id text, page_id text, "
                "workspace_id text partition key)"
            )
            raw_connection.execute(
                "INSERT INTO knowledge_index_config "
                "(id, embedding_model, embedding_version, embedding_dimensions) "
                "VALUES (1, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET embedding_model=excluded.embedding_model, "
                "embedding_version=excluded.embedding_version, "
                "embedding_dimensions=excluded.embedding_dimensions",
                (self._embeddings.model or "unconfigured", self._embeddings.version, dimensions),
            )

        await self._run_sqlite(configure)

    async def _store_vector(self, chunk: KnowledgeChunk, vector: list[float]) -> None:
        serialized = sqlite_vec.serialize_float32(vector)

        def store(raw_connection: sqlite3.Connection) -> None:
            raw_connection.execute(
                f"DELETE FROM {self._VECTOR_TABLE} WHERE chunk_id = ?", (chunk.id,)
            )
            raw_connection.execute(
                f"INSERT INTO {self._VECTOR_TABLE} "
                "(embedding, chunk_id, page_id, workspace_id) VALUES (?, ?, ?, ?)",
                (serialized, chunk.id, chunk.page_id, chunk.workspace_id),
            )

        await self._run_sqlite(store)

    async def _remove_vectors(
        self, chunk_ids: Sequence[str] = (), page_id: str | None = None
    ) -> None:
        def remove(raw_connection: sqlite3.Connection) -> None:
            if page_id is not None:
                raw_connection.execute(
                    f"DELETE FROM {self._VECTOR_TABLE} WHERE page_id = ?", (page_id,)
                )
            elif chunk_ids:
                raw_connection.executemany(
                    f"DELETE FROM {self._VECTOR_TABLE} WHERE chunk_id = ?",
                    [(chunk_id,) for chunk_id in chunk_ids],
                )

        try:
            await self._run_sqlite(remove)
        except sqlite3.OperationalError:
            pass

    async def _nearest(
        self, vector: bytes, workspace_id: str, limit: int
    ) -> list[tuple[str, float]]:
        def search(raw_connection: sqlite3.Connection) -> list[tuple[str, float]]:
            return raw_connection.execute(
                f"SELECT chunk_id, distance FROM {self._VECTOR_TABLE} "
                "WHERE embedding MATCH ? AND k = ? AND workspace_id = ?",
                (vector, limit, workspace_id),
            ).fetchall()

        return await self._run_sqlite(search)

    async def _chunk_vector(self, chunk_id: str) -> bytes | None:
        def get_vector(raw_connection: sqlite3.Connection) -> bytes | None:
            row = raw_connection.execute(
                f"SELECT embedding FROM {self._VECTOR_TABLE} WHERE chunk_id = ?",
                (chunk_id,),
            ).fetchone()
            return None if row is None else bytes(row[0])

        return await self._run_sqlite(get_vector)

    async def index_page(
        self,
        page_id: str,
        expected_page_version: int | None = None,
        expected_generation: int | None = None,
    ) -> PageKnowledge:
        page = await self._session.get(Page, page_id)
        if page is None:
            raise ValueError("page not found")
        initial_page_version = page.version
        if expected_page_version is not None and initial_page_version != expected_page_version:
            raise ValueError("page changed before indexing started")
        specs = _chunk_specs(page, await self._blocks.list_blocks(page_id))
        model = self._embeddings.model or "unconfigured"
        record = await self._session.scalar(
            select(PageKnowledge).where(PageKnowledge.page_id == page_id)
        )
        if record is None:
            record = PageKnowledge(
                page_id=page.id,
                workspace_id=page.workspace_id,
                content_hash="",
                embedding_model=model,
                embedding_version=self._embeddings.version,
                embedding_dimensions=0,
                vector=[],
                concepts=[],
                status="pending",
            )
            self._session.add(record)
            await self._session.flush()
        if expected_generation is not None and record.generation != expected_generation:
            return record
        chunks = list(
            (
                await self._session.scalars(
                    select(KnowledgeChunk).where(KnowledgeChunk.page_knowledge_id == record.id)
                )
            ).all()
        )
        by_key = {chunk.chunk_key: chunk for chunk in chunks}
        configuration_changed = any(
            chunk.embedding_model != model or chunk.embedding_version != self._embeddings.version
            for chunk in chunks
        )
        page_hash = hashlib.sha256("\n".join(spec.text for spec in specs).encode()).hexdigest()
        desired_keys = {spec.key for spec in specs}
        obsolete = [chunk for chunk in chunks if chunk.chunk_key not in desired_keys]
        failed = False
        dimensions = 0
        staged_vectors: dict[str, list[float]] = {}
        for spec in specs:
            content_hash = hashlib.sha256(spec.text.encode()).hexdigest()
            existing_chunk = by_key.get(spec.key)
            reusable = (
                existing_chunk is not None
                and not configuration_changed
                and existing_chunk.content_hash == content_hash
                and existing_chunk.status == "ready"
            )
            if reusable:
                assert existing_chunk is not None
                dimensions = max(dimensions, existing_chunk.embedding_dimensions)
                continue
            try:
                vector = await self._embeddings.embed(spec.text)
                dimensions = len(vector)
                staged_vectors[spec.key] = vector
            except Exception:
                failed = True
                logger.exception(
                    "knowledge embedding failed for page %s chunk %s", page_id, spec.key
                )
        latest_page = await self._session.get(Page, page_id)
        latest_specs = (
            []
            if latest_page is None
            else _chunk_specs(latest_page, await self._blocks.list_blocks(page_id))
        )
        latest_hash = hashlib.sha256(
            "\n".join(spec.text for spec in latest_specs).encode()
        ).hexdigest()
        await self._session.refresh(record)
        if expected_generation is not None and record.generation != expected_generation:
            return record
        if (
            latest_page is None
            or latest_page.version != initial_page_version
            or latest_hash != page_hash
        ):
            record.status = "stale"
            record.error = "Content changed while search was being prepared."
            await self._session.flush()
            return record
        if failed:
            if record.content_hash and record.content_hash != page_hash:
                await self._remove_vectors(page_id=page_id)
                for chunk in chunks:
                    chunk.status = "stale"
                    chunk.error = _INDEX_FAILURE_MESSAGE
            record.status = "failed"
            record.error = _INDEX_FAILURE_MESSAGE
            await self._session.flush()
            return record
        record.content_hash = page_hash
        record.embedding_model = model
        record.embedding_version = self._embeddings.version
        await self._remove_vectors([chunk.id for chunk in obsolete])
        for chunk in obsolete:
            await self._session.delete(chunk)
        await self._ensure_vector_table(dimensions)
        for spec in specs:
            content_hash = hashlib.sha256(spec.text.encode()).hexdigest()
            target_chunk = by_key.get(spec.key)
            if target_chunk is None:
                target_chunk = KnowledgeChunk(
                    page_knowledge_id=record.id,
                    workspace_id=page.workspace_id,
                    page_id=page.id,
                    block_id=spec.block_id,
                    chunk_key=spec.key,
                    chunk_index=spec.index,
                    source_type=spec.source_type,
                    title=spec.title,
                    text=spec.text,
                    content_hash=content_hash,
                    embedding_model=model,
                    embedding_version=self._embeddings.version,
                    embedding_dimensions=0,
                    status="pending",
                )
                self._session.add(target_chunk)
            if spec.key in staged_vectors:
                vector = staged_vectors[spec.key]
                target_chunk.block_id = spec.block_id
                target_chunk.text = spec.text
                target_chunk.content_hash = content_hash
                target_chunk.embedding_model = model
                target_chunk.embedding_version = self._embeddings.version
                target_chunk.embedding_dimensions = len(vector)
                target_chunk.status = "ready"
                target_chunk.indexed_at = datetime.now(UTC)
                target_chunk.error = None
                await self._session.flush()
                await self._store_vector(target_chunk, vector)
        record.embedding_dimensions = dimensions
        record.vector = []
        record.concepts = []
        record.status = "ready"
        record.error = None
        record.indexed_at = datetime.now(UTC)
        await self._session.flush()
        return record

    async def semantic_search(
        self, workspace_id: str, query: str, limit: int = 6
    ) -> list[tuple[KnowledgeChunk, float]]:
        if not query.strip() or limit <= 0:
            return []
        try:
            query_vector = await self._embeddings.embed(query)
            current_config = await self._run_sqlite(
                lambda connection: connection.execute(
                    "SELECT embedding_model, embedding_version, embedding_dimensions "
                    "FROM knowledge_index_config WHERE id = 1"
                ).fetchone()
            )
            expected_config = (
                self._embeddings.model or "unconfigured",
                self._embeddings.version,
                len(query_vector),
            )
            if current_config is not None and tuple(current_config) != expected_config:
                await self._session.execute(
                    update(KnowledgeChunk)
                    .where(KnowledgeChunk.workspace_id == workspace_id)
                    .values(status="stale", error="embedding configuration changed")
                )
                await self._session.execute(
                    update(PageKnowledge)
                    .where(PageKnowledge.workspace_id == workspace_id)
                    .values(status="stale", error="embedding configuration changed")
                )
                await self._session.flush()
            await self._ensure_vector_table(len(query_vector))
            matches = await self._nearest(
                sqlite_vec.serialize_float32(query_vector), workspace_id, limit
            )
        except (httpx.HTTPError, RuntimeError, ValueError, sqlite3.OperationalError) as exc:
            logger.warning(
                "semantic search unavailable; using lexical results for workspace %s: %s",
                workspace_id,
                exc,
            )
            return []
        chunks = await self._session.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.id.in_([item[0] for item in matches]),
                KnowledgeChunk.status == "ready",
                KnowledgeChunk.embedding_model == (self._embeddings.model or "unconfigured"),
                KnowledgeChunk.embedding_version == self._embeddings.version,
                KnowledgeChunk.embedding_dimensions == len(query_vector),
            )
        )
        by_id = {chunk.id: chunk for chunk in chunks}
        return [
            (by_id[chunk_id], 1.0 - distance) for chunk_id, distance in matches if chunk_id in by_id
        ]

    async def related(self, page_id: str, limit: int = 5) -> list[tuple[PageKnowledge, float, str]]:
        if limit <= 0:
            return []
        current = await self._session.scalar(
            select(PageKnowledge).where(PageKnowledge.page_id == page_id)
        )
        if current is None or current.status != "ready":
            return []
        chunks = list(
            (
                await self._session.scalars(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.page_knowledge_id == current.id,
                        KnowledgeChunk.status == "ready",
                    )
                )
            ).all()
        )
        page_scores: dict[str, float] = {}
        matches: list[tuple[str, float]] = []
        for chunk in chunks[:8]:
            vector = await self._chunk_vector(chunk.id)
            if vector is None:
                continue
            matches.extend(await self._nearest(vector, current.workspace_id, limit * 4))
        matched_chunks = await self._session.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.id.in_({chunk_id for chunk_id, _ in matches}),
                KnowledgeChunk.status == "ready",
            )
        )
        by_chunk = {chunk.id: chunk for chunk in matched_chunks}
        for chunk_id, distance in matches:
            match = by_chunk.get(chunk_id)
            if match is not None and match.page_id != page_id:
                page_scores[match.page_id] = max(
                    page_scores.get(match.page_id, 0.0), 1.0 - distance
                )
        pages = await self._session.scalars(
            select(PageKnowledge).where(PageKnowledge.page_id.in_(page_scores))
        )
        by_page = {page.page_id: page for page in pages}
        return [
            (by_page[other_page_id], score, "Similar topic")
            for other_page_id, score in sorted(
                page_scores.items(), key=lambda item: (-item[1], item[0])
            )
            if other_page_id in by_page and score >= 0.55
        ][:limit]

    async def delete_page(self, page_id: str) -> None:
        await self._remove_vectors(page_id=page_id)
        await self._session.execute(delete(PageKnowledge).where(PageKnowledge.page_id == page_id))
