"""make url and date nullable on analytics_snapshots

Revision ID: b1bb6c30e282
Revises: 10a09e43ece5
Create Date: 2025-08-31 20:48:11.427932

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1bb6c30e282"
down_revision: Union[str, Sequence[str], None] = "10a09e43ece5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # No schema changes needed; 'url' and 'date' columns do not exist in analytics_snapshots.
    # This migration is a no-op.


def downgrade() -> None:
    """Downgrade schema."""
    # Nothing to revert; 'url' and 'date' columns are not part of analytics_snapshots.
    # This downgrade is a no-op.
