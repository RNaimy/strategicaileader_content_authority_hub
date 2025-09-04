"""merge heads b1bb6c30e282 + c8576fa3f80f

Revision ID: 4f08b2b289b8
Revises: b1bb6c30e282, c8576fa3f80f
Create Date: 2025-08-31 21:57:06.829074

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f08b2b289b8'
down_revision: Union[str, Sequence[str], None] = ('b1bb6c30e282', 'c8576fa3f80f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
