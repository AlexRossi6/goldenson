"""add recoverable file index health

Revision ID: e1f2a3b4c5d6
Revises: d9e0f1a2b3c4
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("files") as batch_op:
        batch_op.add_column(
            sa.Column(
                "index_status",
                sa.String(length=20),
                nullable=False,
                server_default="metadata_only",
            )
        )
        batch_op.add_column(sa.Column("index_error", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("search_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("content_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("index_generation", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE files SET index_status = 'stale' "
        "WHERE mime_type LIKE 'text/%' OR mime_type IN ('application/json', 'application/xml')"
    )


def downgrade() -> None:
    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_column("indexed_at")
        batch_op.drop_column("index_generation")
        batch_op.drop_column("content_hash")
        batch_op.drop_column("search_text")
        batch_op.drop_column("index_error")
        batch_op.drop_column("index_status")
