from __future__ import annotations

from typing import Protocol

import httpx


class EmbeddingProvider(Protocol):
    model: str
    version: str
    dimensions: int

    async def embed(self, text: str) -> list[float]: ...


class OllamaEmbeddingProvider:
    """Embedding provider backed by the explicitly configured local Ollama runtime."""

    def __init__(
        self,
        base_url: str,
        model: str,
        version: str = "ollama-api-v1",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self.version = version
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self.dimensions = 0

    async def embed(self, text: str) -> list[float]:
        if not self.model:
            raise RuntimeError("a local embedding model is not configured")
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            trust_env=False,
        ) as client:
            response = await client.post("/api/embed", json={"model": self.model, "input": text})
        response.raise_for_status()
        payload = response.json()
        embeddings = payload.get("embeddings")
        if (
            not isinstance(embeddings, list)
            or not embeddings
            or not isinstance(embeddings[0], list)
        ):
            raise RuntimeError("Ollama returned an invalid embedding response")
        vector = embeddings[0]
        if not all(isinstance(value, (int, float)) for value in vector):
            raise RuntimeError("Ollama returned a non-numeric embedding")
        self.dimensions = len(vector)
        return [float(value) for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))
