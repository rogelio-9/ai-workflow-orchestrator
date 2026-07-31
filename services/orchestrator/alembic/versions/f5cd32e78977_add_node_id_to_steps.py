"""add node_id to steps

Revision ID: f5cd32e78977
Revises: 44041167de73
Create Date: 2026-07-31 14:19:34.212694

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5cd32e78977'
down_revision: Union[str, Sequence[str], None] = '44041167de73'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    node_id is the DAG node's own identifier ("summarize"), the join key
    between dag_json and this table. Without it a Kafka message naming a node
    cannot be resolved to the steps row that step_results must reference.

    Added in three steps rather than one: a populated table cannot take a NOT
    NULL column directly, because existing rows have no value for it. Add
    nullable, backfill, then constrain.
    """
    op.add_column("steps", sa.Column("node_id", sa.Text(), nullable=True))

    # Rows predating this column have no DAG node to point at. The synthetic
    # value is prefixed so it is obviously not a real node id.
    op.execute("UPDATE steps SET node_id = 'legacy-' || id::text WHERE node_id IS NULL")

    op.alter_column("steps", "node_id", nullable=False)

    # Unique per workflow, not globally: two workflows are both allowed a node
    # called "summarize".
    op.create_unique_constraint(
        "uq_steps_workflow_node", "steps", ["workflow_id", "node_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_steps_workflow_node", "steps", type_="unique")
    op.drop_column("steps", "node_id")
