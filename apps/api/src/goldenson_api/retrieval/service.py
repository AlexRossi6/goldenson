from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.services.block_service import BlockService
from goldenson_api.services.errors import NotFoundError
from goldenson_api.services.file_service import FileService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class RetrievedSource(BaseModel):
    kind: Literal["page", "block", "file"]
    title: str
    snippet: str
    page_id: str | None = None
    block_id: str | None = None
    file_id: str | None = None
    score: float = Field(ge=0)


class RetrievalResult(BaseModel):
    context: str
    sources: list[RetrievedSource]


class RelatedContentItem(BaseModel):
    page_id: str
    title: str
    snippet: str
    block_id: str | None = None


class RelatedContentResult(BaseModel):
    items: list[RelatedContentItem]


_SEMANTIC_WEIGHT = 0.55
_KEYWORD_WEIGHT = 0.45
_TITLE_BONUS = 0.25
_SOURCE_BONUS = {"page": 0.05, "block": 0.02, "file": 0.0}
_RELATED_MIN_SCORE = 0.25
_RELATED_PASSAGE_LENGTH = 1200
_RELATED_PASSAGE_LIMIT = 8


def _keyword_score(query: str, title: str, text: str) -> float:
    query_tokens = {token.lower() for token in _TOKEN_PATTERN.findall(query)}
    document_tokens = {token.lower() for token in _TOKEN_PATTERN.findall(f"{title} {text}")}
    if not query_tokens or not document_tokens:
        return 0.0
    coverage = len(query_tokens & document_tokens) / len(query_tokens)
    normalized_query = " ".join(query.lower().split())
    normalized_text = " ".join(f"{title} {text}".lower().split())
    phrase_bonus = 0.5 if normalized_query and normalized_query in normalized_text else 0.0
    title_tokens = {token.lower() for token in _TOKEN_PATTERN.findall(title)}
    title_bonus = 0.35 if query_tokens <= title_tokens else 0.0
    return min(1.0, coverage + phrase_bonus + title_bonus)


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
    return "\n".join(parts)


class WorkspaceRetrievalService:
    def __init__(self, session: AsyncSession) -> None:
        self._pages = PageService(session)
        self._blocks = BlockService(session)
        self._files = FileService(session)
        self._knowledge = KnowledgeService(session)

    async def search(
        self,
        workspace_id: str,
        query: str,
        limit: int = 6,
        *,
        exclude_page_id: str | None = None,
    ) -> RetrievalResult:
        if not query.strip() or limit <= 0:
            return RetrievalResult(context="", sources=[])

        candidates: dict[tuple[str, str | None, str | None], RetrievedSource] = {}
        pages = await self._pages.list_pages(workspace_id)
        semantic_results = await self._knowledge.semantic_search(
            workspace_id, query, limit=max(limit * 3, 6)
        )
        semantic_scores: dict[str, float] = {}
        semantic_block_scores: dict[tuple[str, str], float] = {}
        semantic_snippets: dict[str, str] = {}
        for chunk, score in semantic_results:
            semantic_scores[chunk.page_id] = max(semantic_scores.get(chunk.page_id, 0.0), score)
            semantic_snippets.setdefault(chunk.page_id, chunk.text)
            if chunk.block_id is not None:
                key = (chunk.page_id, chunk.block_id)
                semantic_block_scores[key] = max(semantic_block_scores.get(key, 0.0), score)

        for page in pages:
            if page.id == exclude_page_id:
                continue
            blocks = await self._blocks.list_blocks(page.id)
            page_body = "\n".join(_block_text(block.content) for block in blocks)
            keyword_score = _keyword_score(query, page.title, page_body)
            semantic_score = semantic_scores.get(page.id, 0.0)
            page_score = (
                semantic_score * _SEMANTIC_WEIGHT
                + keyword_score * _KEYWORD_WEIGHT
                + (_TITLE_BONUS if keyword_score and query.lower() in page.title.lower() else 0.0)
                + (_SOURCE_BONUS["page"] if semantic_score or keyword_score else 0.0)
            )
            if page_score > 0:
                source = RetrievedSource(
                    kind="page",
                    title=page.title,
                    snippet=semantic_snippets.get(page.id, page_body)[:500] or page.title,
                    page_id=page.id,
                    score=page_score,
                )
                candidates[("page", page.id, None)] = source
            for block in blocks:
                text = _block_text(block.content)
                block_keyword_score = _keyword_score(query, page.title, text)
                block_semantic_score = semantic_block_scores.get((page.id, block.id), 0.0)
                block_score = (
                    block_semantic_score * _SEMANTIC_WEIGHT
                    + block_keyword_score * _KEYWORD_WEIGHT
                    + (
                        _SOURCE_BONUS["block"]
                        if block_semantic_score or block_keyword_score
                        else 0.0
                    )
                )
                if text and block_score > 0:
                    candidates[("block", page.id, block.id)] = RetrievedSource(
                        kind="block",
                        title=page.title,
                        snippet=text[:500],
                        page_id=page.id,
                        block_id=block.id,
                        score=block_score,
                    )

        for file_metadata in await self._files.list_workspace_files(workspace_id):
            if exclude_page_id is not None and file_metadata.page_id == exclude_page_id:
                continue
            searchable_text = getattr(file_metadata, "search_text", None) or ""
            file_score = _keyword_score(query, file_metadata.name, searchable_text)
            if file_score > 0:
                candidates[("file", file_metadata.page_id, file_metadata.id)] = RetrievedSource(
                    kind="file",
                    title=file_metadata.name,
                    snippet=searchable_text[:500] or file_metadata.name,
                    page_id=file_metadata.page_id,
                    file_id=file_metadata.id,
                    score=file_score * _KEYWORD_WEIGHT + _SOURCE_BONUS["file"],
                )

        sources = sorted(
            candidates.values(),
            key=lambda source: (
                -source.score,
                source.kind,
                source.title.casefold(),
                source.snippet,
                source.page_id or "",
                source.block_id or source.file_id or "",
            ),
        )[:limit]
        context_parts = [
            f"SOURCE {index + 1}: {source.title}\n{source.snippet}"
            for index, source in enumerate(sources)
        ]
        return RetrievalResult(context="\n\n".join(context_parts)[:12000], sources=sources)

    async def related(self, page_id: str, limit: int = 5) -> RelatedContentResult:
        if limit <= 0:
            return RelatedContentResult(items=[])
        page = await self._pages.get_page(page_id)
        if page is None:
            raise NotFoundError("page not found")
        blocks = await self._blocks.list_blocks(page.id)
        passages = []
        for passage in [page.title, *(_block_text(block.content) for block in blocks)]:
            normalized = passage.strip()[:_RELATED_PASSAGE_LENGTH]
            if len(_TOKEN_PATTERN.findall(normalized)) >= 2 and normalized not in passages:
                passages.append(normalized)
            if len(passages) == _RELATED_PASSAGE_LIMIT:
                break
        if not passages:
            return RelatedContentResult(items=[])

        by_page: dict[str, tuple[float, RetrievedSource, RetrievedSource | None]] = {}
        for passage in passages:
            result = await self.search(
                page.workspace_id,
                passage,
                limit=max(limit * 8, 24),
                exclude_page_id=page.id,
            )
            for source in result.sources:
                if source.page_id is None or source.score < _RELATED_MIN_SCORE:
                    continue
                existing = by_page.get(source.page_id)
                if existing is None:
                    by_page[source.page_id] = (
                        source.score,
                        source,
                        source if source.kind == "block" else None,
                    )
                    continue
                score, strongest, block_evidence = existing
                if source.score > score:
                    score, strongest = source.score, source
                if source.kind == "block" and (
                    block_evidence is None or source.score > block_evidence.score
                ):
                    block_evidence = source
                by_page[source.page_id] = (score, strongest, block_evidence)

        items = []
        for destination_page_id, (_, strongest, block_evidence) in sorted(
            by_page.items(),
            key=lambda item: (-item[1][0], item[0]),
        )[:limit]:
            evidence = block_evidence or strongest
            destination = await self._pages.get_page(destination_page_id)
            if destination is None:
                continue
            items.append(
                RelatedContentItem(
                    page_id=destination_page_id,
                    title=destination.title,
                    snippet=evidence.snippet,
                    block_id=evidence.block_id,
                )
            )
        return RelatedContentResult(items=items)
