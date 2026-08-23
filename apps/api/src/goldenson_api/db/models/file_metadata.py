from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from goldenson_api.db.base import Base

if TYPE_CHECKING:
    from goldenson_api.db.models.page import Page
    from goldenson_api.db.models.workspace import Workspace


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FileMetadata(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_id: Mapped[str | None] = mapped_column(
        ForeignKey("pages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    index_status: Mapped[str] = mapped_column(String(20), nullable=False, default="metadata_only")
    index_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    index_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    workspace: Mapped[Workspace] = relationship(back_populates="files")
    page: Mapped[Page | None] = relationship(back_populates="files")

    @property
    def content_searchable(self) -> bool:
        return self.search_text is not None
