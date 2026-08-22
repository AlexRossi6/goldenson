from __future__ import annotations

import math
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.services.block_service import BlockService
from goldenson_api.services.file_service import FileService
from goldenson_api.services.page_service import PageService

_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]+", re.IGNORECASE)


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


def _tokens(value: str) -> Counter[str]:
    return Counter(token.lower() for token in _TOKEN_PATTERN.findall(value))


def _score(query: Counter[str], document: Counter[str]) -> float:
    if not query or not document:
        return 0.0
    overlap = sum(query[token] * document[token] for token in query)
    query_norm = math.sqrt(sum(value * value for value in query.values()))
    document_norm = math.sqrt(sum(value * value for value in document.values()))
    return overlap / (query_norm * document_norm) if overlap else 0.0


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

    async def search(self, workspace_id: str, query: str, limit: int = 6) -> RetrievalResult:
        query_tokens = _tokens(query)
        candidates: list[RetrievedSource] = []
        pages = await self._pages.list_pages(workspace_id)

        for page in pages:
            blocks = await self._blocks.list_blocks(page.id)
            page_body = "\n".join(_block_text(block.content) for block in blocks)
            page_score = _score(query_tokens, _tokens(f"{page.title}\n{page_body}"))
            if page_score > 0:
                candidates.append(
                    RetrievedSource(
                        kind="page",
                        title=page.title,
                        snippet=page_body[:500] or page.title,
                        page_id=page.id,
                        score=page_score,
                    )
                )
            for block in blocks:
                text = _block_text(block.content)
                block_score = _score(query_tokens, _tokens(f"{page.title}\n{text}"))
                if text and block_score > 0:
                    candidates.append(
                        RetrievedSource(
                            kind="block",
                            title=page.title,
                            snippet=text[:500],
                            page_id=page.id,
                            block_id=block.id,
                            score=block_score,
                        )
                    )

        for file_metadata in await self._files.list_workspace_files(workspace_id):
            file_score = _score(query_tokens, _tokens(file_metadata.name))
            if file_score > 0:
                candidates.append(
                    RetrievedSource(
                        kind="file",
                        title=file_metadata.name,
                        snippet=file_metadata.name,
                        page_id=file_metadata.page_id,
                        file_id=file_metadata.id,
                        score=file_score,
                    )
                )

        sources = sorted(candidates, key=lambda source: source.score, reverse=True)[:limit]
        context_parts = [
            f"SOURCE {index + 1}: {source.title}\n{source.snippet}"
            for index, source in enumerate(sources)
        ]
        return RetrievalResult(context="\n\n".join(context_parts)[:12000], sources=sources)
