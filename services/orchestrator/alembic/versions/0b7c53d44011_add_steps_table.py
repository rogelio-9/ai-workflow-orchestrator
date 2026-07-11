"""add steps table

Revision ID: 0b7c53d44011
Revises: de155c8182dc
Create Date: 2026-07-11 11:00:38.981834

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0b7c53d44011'
down_revision: Union[str, Sequence[str], None] = 'de155c8182dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "steps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workflow_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("depends_on", postgresql.ARRAY(postgresql.UUID(as_uuid=True))),
        sa.Column("step_order", sa.Integer()),
        sa.Column("retry_policy", postgresql.JSONB()),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
    )


def downgrade() -> None:
    op.drop_table("steps")
