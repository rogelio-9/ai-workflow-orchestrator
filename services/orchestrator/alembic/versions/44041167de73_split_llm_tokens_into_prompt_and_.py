"""split llm_tokens into prompt and completion

Revision ID: 44041167de73
Revises: d990eb287426
Create Date: 2026-07-31 12:32:22.529537

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44041167de73'
down_revision: Union[str, Sequence[str], None] = 'd990eb287426'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    The gateway reports prompt and completion tokens separately because every
    provider bills input and output at different rates; a single total cannot
    be split back apart afterwards. Existing llm_tokens values are dropped
    rather than guessed at -- there is no honest mapping from a total to
    either half.
    """
    op.add_column("step_results", sa.Column("prompt_tokens", sa.Integer()))
    op.add_column("step_results", sa.Column("completion_tokens", sa.Integer()))
    op.drop_column("step_results", "llm_tokens")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("step_results", sa.Column("llm_tokens", sa.Integer()))
    op.drop_column("step_results", "prompt_tokens")
    op.drop_column("step_results", "completion_tokens")
