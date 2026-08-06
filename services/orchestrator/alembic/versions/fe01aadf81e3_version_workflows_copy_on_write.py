"""version workflows copy on write

Revision ID: fe01aadf81e3
Revises: f5cd32e78977
Create Date: 2026-08-05 21:47:14.384023

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fe01aadf81e3'
down_revision: Union[str, Sequence[str], None] = 'f5cd32e78977'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Editing a workflow used to delete and recreate its steps rows, which the
    step_results foreign key refuses once any run has recorded results. So a
    workflow became uneditable the moment it was first run -- fatal for a
    visual builder, where editing something you just ran is the normal case.

    Copy-on-write instead: an edit bumps workflows.version and writes a fresh
    set of steps rows at that version. Nothing is deleted, so old results keep
    pointing at the graph that actually produced them.
    """
    # Immutable snapshot per version. workflows.dag_json stays as the current
    # editable copy; this is the history a run can be replayed against, since
    # dag_json is overwritten on every edit.
    op.create_table(
        "workflow_versions",
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workflows.id"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("dag_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.execute(
        "INSERT INTO workflow_versions (workflow_id, version, dag_json) "
        "SELECT id, version, dag_json FROM workflows"
    )

    # Nullable -> backfill -> constrain: the table has rows, so NOT NULL
    # cannot go on in one step.
    op.add_column("steps", sa.Column("version", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE steps s SET version = w.version FROM workflows w "
        "WHERE w.id = s.workflow_id AND s.version IS NULL"
    )
    op.alter_column("steps", "version", nullable=False)

    # A node id is now unique per version, not per workflow -- the whole point
    # is that "summarize" exists at v1 and again at v2.
    op.drop_constraint("uq_steps_workflow_node", "steps", type_="unique")
    op.create_unique_constraint(
        "uq_steps_workflow_node_version", "steps",
        ["workflow_id", "node_id", "version"],
    )

    # A run is pinned at creation. Without this a retry would resume against
    # whatever the graph looks like now, not the one it started on.
    op.add_column("runs", sa.Column("workflow_version", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE runs r SET workflow_version = w.version FROM workflows w "
        "WHERE w.id = r.workflow_id AND r.workflow_version IS NULL"
    )
    op.alter_column("runs", "workflow_version", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("runs", "workflow_version")
    op.drop_constraint("uq_steps_workflow_node_version", "steps", type_="unique")
    op.create_unique_constraint(
        "uq_steps_workflow_node", "steps", ["workflow_id", "node_id"]
    )
    op.drop_column("steps", "version")
    op.drop_table("workflow_versions")
