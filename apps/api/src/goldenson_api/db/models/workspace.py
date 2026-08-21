from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from goldenson_api.db.base import Base

if TYPE_CHECKING:
    from goldenson_api.db.models.file_metadata import FileMetadata
    from goldenson_api.db.models.page import Page


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )

    pages: Mapped[list[Page]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
    files: Mapped[list[FileMetadata]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )
