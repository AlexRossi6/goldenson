"""agent audit trail

Revision ID: 7a43c2d9e510
Revises: 06b05beb32e0
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7a43c2d9e510"
down_revision: str | Sequence[str] | None = "06b05beb32e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("request", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_runs_workspace_id"), "agent_runs", ["workspace_id"])
    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("provider_call_id", sa.String(length=255), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("permission", sa.String(length=20), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("approval_state", sa.String(length=20), nullable=False),
        sa.Column("result_summary", sa.String(length=500), nullable=True),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_tool_calls_run_id"), "agent_tool_calls", ["run_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_tool_calls_run_id"), table_name="agent_tool_calls")
    op.drop_table("agent_tool_calls")
    op.drop_index(op.f("ix_agent_runs_workspace_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
