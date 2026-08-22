from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from goldenson_api.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LocalAISettings(Base):
    __tablename__ = "local_ai_settings"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default="default")
    selected_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now
    )
