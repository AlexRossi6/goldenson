"""page knowledge index

Revision ID: 9d6f2c1a4b7e
Revises: c2f493ea8d31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9d6f2c1a4b7e"
down_revision: str | Sequence[str] | None = "c2f493ea8d31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_index_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_version", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
    )
    op.create_table(
        "page_knowledge",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("page_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_version", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("vector", sa.JSON(), nullable=False),
        sa.Column("concepts", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["page_id"], ["pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("page_id", name="uq_page_knowledge_page"),
    )
    op.create_index("ix_page_knowledge_page_id", "page_knowledge", ["page_id"])
    op.create_index("ix_page_knowledge_workspace_id", "page_knowledge", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("page_knowledge")
    op.drop_table("knowledge_index_config")
