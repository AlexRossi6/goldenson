

from __future__ import annotations

import logging
import re
import time
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.services.block_service import BlockService
from goldenson_api.services.errors import NotFoundError
from goldenson_api.services.file_service import FileService
from goldenson_api.services.knowledge_service import KnowledgeService
from goldenson_api.services.page_service import PageService

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_QUERY_STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "please",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
    "workspace",
}


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
    answer_sources: list[RetrievedSource] | None = Field(default=None, exclude=True)


class RelatedContentItem(BaseModel):
    page_id: str
    title: str
    snippet: str
    block_id: str | None = None


class RelatedContentResult(BaseModel):
    items: list[RelatedContentItem]


_SEMANTIC_WEIGHT = 0.55
_SEMANTIC_MIN_SCORE = 0.35
_KEYWORD_WEIGHT = 0.45
_TITLE_BONUS = 0.25
_SOURCE_BONUS = {"page": 0.05, "block": 0.02, "file": 0.0}
_RELATED_MIN_SCORE = 0.25
_RELATED_PASSAGE_LENGTH = 1200
_RELATED_PASSAGE_LIMIT = 8

# Answer-aware source rescoring (experiment)
_ANSWER_EMBEDDING_MIN_LENGTH = 15  # Require enough tokens for meaningful embedding
_ANSWER_SEMANTIC_WEIGHT = 0.35  # Lower than retrieval semantic weight; additive signal
_ANSWER_SCORE_THRESHOLD = 0.25  # Minimum answer/source similarity to count


def _keyword_score(query: str, title: str, text: str) -> float:
    raw_query_tokens = {token.lower() for token in _TOKEN_PATTERN.findall(query)}
    query_tokens = raw_query_tokens - _QUERY_STOP_WORDS
    if not query_tokens:
        query_tokens = raw_query_tokens
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


def _source_sort_key(source: RetrievedSource) -> tuple[float, str, str, str, str, str]:
    return (
        -source.score,
        source.kind,
        source.title.casefold(),
        source.snippet,
        source.page_id or "",
        source.block_id or source.file_id or "",
    )


def _compact_sources(sources: list[RetrievedSource]) -> list[RetrievedSource]:
    block_page_ids = {source.page_id for source in sources if source.kind == "block"}
    page_scores = {
        source.page_id: source.score
        for source in sources
        if source.kind == "page" and source.page_id is not None
    }
    seen_blocks: set[tuple[str | None, str]] = set()
    compacted: list[RetrievedSource] = []
    for source in sources:
        if source.kind == "page" and source.page_id in block_page_ids:
            continue
        if source.kind == "block" and source.block_id is not None:
            block_key = (source.page_id, source.block_id)
            if block_key in seen_blocks:
                continue
            seen_blocks.add(block_key)
            page_score = page_scores.get(source.page_id, 0.0) if source.page_id is not None else 0.0
            if page_score > source.score:
                source = source.model_copy(update={"score": page_score})
        compacted.append(source)
    return compacted


def _select_answer_sources(query: str, sources: list[RetrievedSource]) -> list[RetrievedSource]:
    """Keep visible evidence focused when semantic retrieval has broad candidates."""
    if not sources:
        return []

    lexical_scores = [
        (source, _keyword_score(query, source.title, source.snippet)) for source in sources
    ]
    lexical_matches = [(source, score) for source, score in lexical_scores if score > 0]
    if not lexical_matches:
        return sources

    strongest_score = max(score for _, score in lexical_matches)
    minimum_score = max(0.15, strongest_score * 0.5)
    return [source for source, score in lexical_matches if score >= minimum_score]


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
            if score < _SEMANTIC_MIN_SCORE:
                continue
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

        ranked_sources = sorted(
            candidates.values(),
            key=_source_sort_key,
        )
        compacted_sources = _compact_sources(ranked_sources)
        sources = sorted(compacted_sources, key=_source_sort_key)[:limit]
        context_parts = [
            f"SOURCE {index + 1}: {source.title}\n{source.snippet}"
            for index, source in enumerate(sources)
        ]
        return RetrievalResult(
            context="\n\n".join(context_parts)[:12000],
            sources=sources,
            answer_sources=_select_answer_sources(query, sources),
        )

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

    async def rescore_sources_by_answer(
        self,
        answer: str,
        query: str,
        sources: list[RetrievedSource],
    ) -> tuple[list[RetrievedSource], float]:
        """
        Rescore candidate sources based on their semantic similarity to the final answer.
        
        This is an experiment to improve source selection by combining the answer's
        embedding with existing deterministic relevance signals.
        
        Returns:
            (rescored_sources, embedding_latency_ms)
        """
        if not sources or not answer.strip():
            return sources, 0.0
        
        # Don't embed very short answers
        if len(answer.split()) < _ANSWER_EMBEDDING_MIN_LENGTH:
            return sources, 0.0
        
        embedding_started = time.monotonic()
        try:
            # Attempt to embed the answer
            answer_embedding = await self._knowledge.embed_text(answer)
            if not answer_embedding:
                return sources, 0.0
        except Exception as e:
            logger.debug("answer embedding failed: %s; falling back to deterministic scoring", e)
            return sources, 0.0
        
        embedding_latency_ms = (time.monotonic() - embedding_started) * 1000
        
        # Score each source against the answer embedding
        rescored: list[tuple[RetrievedSource, float]] = []
        for source in sources:
            # Use snippet as the source text; it's what would be displayed
            source_text = source.snippet
            try:
                source_embedding = await self._knowledge.embed_text(source_text)
                if not source_embedding:
                    rescored.append((source, source.score))
                    continue
                
                # Compute semantic similarity (normalized dot product)
                if len(answer_embedding) != len(source_embedding):
                    similarity = 0.0
                else:
                    dot_product = sum(
                        a * b for a, b in zip(answer_embedding, source_embedding, strict=True)
                    )
                    mag_answer = sum(a * a for a in answer_embedding) ** 0.5
                    mag_source = sum(b * b for b in source_embedding) ** 0.5
                    if mag_answer > 0 and mag_source > 0:
                        similarity = dot_product / (mag_answer * mag_source)
                    else:
                        similarity = 0.0
                
                if similarity < _ANSWER_SCORE_THRESHOLD:
                    similarity = 0.0
                
                # Combine with existing score: boost strong matches, keep weak ones visible
                combined_score = source.score + (similarity * _ANSWER_SEMANTIC_WEIGHT)
                rescored_source = source.model_copy(update={"score": combined_score})
                rescored.append((rescored_source, similarity))
            except Exception as e:
                logger.debug("source embedding failed for %s: %s; keeping original score", 
                           source.page_id, e)
                rescored.append((source, 0.0))
        
        # Re-select answer sources using combined scores
        combined_sources = [source for source, _ in rescored]
        answer_sources = _select_answer_sources(query, combined_sources)
        
        return answer_sources, embedding_latency_ms
