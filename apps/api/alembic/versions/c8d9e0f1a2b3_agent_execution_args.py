"""preserve validated agent execution arguments

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | Sequence[str] | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_tool_calls") as batch_op:
        batch_op.add_column(sa.Column("execution_arguments", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_calls") as batch_op:
        batch_op.drop_column("execution_arguments")
