from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogModel:
    id: str
    name: str
    size_bytes: int
    required_disk_bytes: int
    role: str
    minimum_memory_bytes: int


GIB = 1024**3
MODEL_CATALOG: tuple[CatalogModel, ...] = (
    CatalogModel(
        id="llama3.2:3b",
        name="Llama 3.2 3B",
        size_bytes=2 * GIB,
        required_disk_bytes=3 * GIB,
        role="Fast general assistant for smaller computers",
        minimum_memory_bytes=8 * GIB,
    ),
    CatalogModel(
        id="gemma3:4b",
        name="Gemma 3 4B",
        size_bytes=int(3.3 * GIB),
        required_disk_bytes=4 * GIB,
        role="Efficient writing and summarization",
        minimum_memory_bytes=8 * GIB,
    ),
    CatalogModel(
        id="qwen3:8b",
        name="Qwen 3 8B",
        size_bytes=int(5.2 * GIB),
        required_disk_bytes=6 * GIB,
        role="Balanced reasoning and workspace assistance",
        minimum_memory_bytes=16 * GIB,
    ),
    CatalogModel(
        id="qwen3:14b",
        name="Qwen 3 14B",
        size_bytes=9 * GIB,
        required_disk_bytes=11 * GIB,
        role="Higher-quality reasoning for capable computers",
        minimum_memory_bytes=24 * GIB,
    ),
)
MODEL_CATALOG_BY_ID = {model.id: model for model in MODEL_CATALOG}
