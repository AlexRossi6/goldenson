"""repair missing page knowledge generation column

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e0f1a2b3c4"
down_revision: str | Sequence[str] | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("page_knowledge")}
    if "generation" not in columns:
        with op.batch_alter_table("page_knowledge") as batch_op:
            batch_op.add_column(
                sa.Column("generation", sa.Integer(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    pass
