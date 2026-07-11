"""add step_results and indexes

Revision ID: d990eb287426
Revises: 0b7c53d44011
Create Date: 2026-07-11 11:07:10.904243

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd990eb287426'
down_revision: Union[str, Sequence[str], None] = '0b7c53d44011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "step_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text()),
        sa.Column("output_json", postgresql.JSONB()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("llm_tokens", sa.Integer()),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempt", sa.Integer(), server_default="1"),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"]),
        sa.ForeignKeyConstraint(["step_id"], ["steps.id"]),
    )

    op.create_index("idx_runs_workflow_status", "runs", ["workflow_id", "status"])
    op.create_index("idx_runs_started_at", "runs", [sa.text("started_at DESC")])
    op.create_index("idx_step_results_run_id", "step_results", ["run_id"])
    op.create_index("idx_step_results_step_id", "step_results", ["step_id"])


def downgrade() -> None:
    op.drop_index("idx_step_results_step_id", table_name="step_results")
    op.drop_index("idx_step_results_run_id", table_name="step_results")
    op.drop_index("idx_runs_started_at", table_name="runs")
    op.drop_index("idx_runs_workflow_status", table_name="runs")
    op.drop_table("step_results")
