"""定时调度字段 + 覆盖率表

Revision ID: 0002
Revises: 0001
Create Date: 2025-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# 与 app/db/base.py 的 JSONType 保持一致
JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # TE-04：定时调度
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column("schedule_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch.add_column(sa.Column("schedule_interval_minutes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("last_scheduled_at", sa.DateTime(timezone=True), nullable=True))

    # RP-02：覆盖率
    op.create_table(
        "coverage_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("line_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("branch_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("total_lines", sa.Integer(), nullable=False),
        sa.Column("covered_lines", sa.Integer(), nullable=False),
        sa.Column("total_branches", sa.Integer(), nullable=False),
        sa.Column("covered_branches", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("raw", JSON_TYPE, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_coverage_reports_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["executions.id"],
            name=op.f("fk_coverage_reports_execution_id_executions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coverage_reports")),
    )
    op.create_index(
        op.f("ix_coverage_reports_project_id"), "coverage_reports", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_coverage_reports_execution_id"),
        "coverage_reports",
        ["execution_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_coverage_reports_execution_id"), table_name="coverage_reports")
    op.drop_index(op.f("ix_coverage_reports_project_id"), table_name="coverage_reports")
    op.drop_table("coverage_reports")

    with op.batch_alter_table("projects") as batch:
        batch.drop_column("last_scheduled_at")
        batch.drop_column("schedule_interval_minutes")
        batch.drop_column("schedule_enabled")