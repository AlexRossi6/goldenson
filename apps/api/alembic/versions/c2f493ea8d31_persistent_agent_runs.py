"""persistent agent runs

Revision ID: c2f493ea8d31
Revises: 8b91d134a620
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c2f493ea8d31"
down_revision: str | Sequence[str] | None = "8b91d134a620"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("messages", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(
            sa.Column("tool_call_count", sa.Integer(), server_default="0", nullable=False)
        )
        batch_op.add_column(
            sa.Column("remaining_seconds", sa.Float(), server_default="60", nullable=False)
        )
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE agent_runs SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.alter_column("updated_at", nullable=False)
        batch_op.alter_column("messages", server_default=None)
        batch_op.alter_column("tool_call_count", server_default=None)
        batch_op.alter_column("remaining_seconds", server_default=None)

    with op.batch_alter_table("agent_tool_calls") as batch_op:
        batch_op.add_column(sa.Column("result", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_calls") as batch_op:
        batch_op.drop_column("decision_at")
        batch_op.drop_column("result")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_column("updated_at")
        batch_op.drop_column("remaining_seconds")
        batch_op.drop_column("tool_call_count")
        batch_op.drop_column("messages")
