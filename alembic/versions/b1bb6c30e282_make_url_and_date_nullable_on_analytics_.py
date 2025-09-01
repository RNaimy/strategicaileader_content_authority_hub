"""make url and date nullable on analytics_snapshots

Revision ID: b1bb6c30e282
Revises: 10a09e43ece5
Create Date: 2025-08-31 20:48:11.427932

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1bb6c30e282'
down_revision: Union[str, Sequence[str], None] = '10a09e43ece5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('analytics_snapshots') as batch_op:
        # Make 'url' nullable
        batch_op.alter_column(
            'url',
            existing_type=sa.Text(),
            nullable=True,
        )
        # Make 'date' nullable
        batch_op.alter_column(
            'date',
            existing_type=sa.DateTime(),
            nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('analytics_snapshots') as batch_op:
        # Revert 'url' to NOT NULL
        batch_op.alter_column(
            'url',
            existing_type=sa.Text(),
            nullable=False,
        )
        # Revert 'date' to NOT NULL
        batch_op.alter_column(
            'date',
            existing_type=sa.DateTime(),
            nullable=False,
        )
