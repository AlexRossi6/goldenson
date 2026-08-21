from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from goldenson_api.db.base import Base

if TYPE_CHECKING:
    from goldenson_api.db.models.block import Block
    from goldenson_api.db.models.file_metadata import FileMetadata
    from goldenson_api.db.models.workspace import Workspace


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_page_id: Mapped[str | None] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    workspace: Mapped[Workspace] = relationship(back_populates="pages")
    parent_page: Mapped[Page | None] = relationship(
        back_populates="child_pages", remote_side="Page.id"
    )
    child_pages: Mapped[list[Page]] = relationship(
        back_populates="parent_page", cascade="all, delete-orphan"
    )
    blocks: Mapped[list[Block]] = relationship(back_populates="page", cascade="all, delete-orphan")
    files: Mapped[list[FileMetadata]] = relationship(back_populates="page")
