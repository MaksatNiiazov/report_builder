"""Create report builder tables.

Revision ID: 20260716_0001
Revises:
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260716_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_data_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("engine", sa.String(length=30), nullable=False),
        sa.Column("encrypted_dsn", sa.Text(), nullable=False),
        sa.Column("allowed_schemas", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_report_data_sources_name", "report_data_sources", ["name"])
    op.create_index("ix_report_data_sources_is_active", "report_data_sources", ["is_active"])
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_source_id", sa.Integer(), nullable=False),
        sa.Column("query_template", sa.Text(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("default_row_limit", sa.Integer(), nullable=False),
        sa.Column("max_row_limit", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_source_id"], ["report_data_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_reports_slug", "reports", ["slug"])
    op.create_index("ix_reports_name", "reports", ["name"])
    op.create_index("ix_reports_data_source_id", "reports", ["data_source_id"])
    op.create_index("ix_reports_is_published", "reports", ["is_published"])
    op.create_table(
        "report_executions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("output_format", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_executions_report_id", "report_executions", ["report_id"])
    op.create_index("ix_report_executions_actor", "report_executions", ["actor"])
    op.create_index("ix_report_executions_status", "report_executions", ["status"])
    op.create_index("ix_report_executions_started_at", "report_executions", ["started_at"])


def downgrade() -> None:
    op.drop_table("report_executions")
    op.drop_table("reports")
    op.drop_table("report_data_sources")

