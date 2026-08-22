"""local AI settings

Revision ID: 8b91d134a620
Revises: 7a43c2d9e510
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8b91d134a620"
down_revision: str | Sequence[str] | None = "7a43c2d9e510"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_ai_settings",
        sa.Column("id", sa.String(length=20), nullable=False),
        sa.Column("selected_model", sa.String(length=100), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("local_ai_settings")
