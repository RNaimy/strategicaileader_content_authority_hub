"""merge: phase9 + phase8 heads

Revision ID: 20250903_merge_phase9_phase8
Revises: 20250903_phase9_retrieval, 3391bd7240f4
Create Date: 2025-09-03 18:33:43.238189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20250903_merge_phase9_phase8'
down_revision: Union[str, Sequence[str], None] = ('20250903_phase9_retrieval', '3391bd7240f4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
