"""index url/cluster id + add timestamps migration (restored header)

Revision ID: cd3e89114a5c
Revises: eac32663f359
Create Date: 2025-01-01
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "cd3e89114a5c"
down_revision: Union[str, Sequence[str], None] = "c83bddaeb395"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This migration header was accidentally overwritten.
    # Restore as a NO-OP to preserve the Alembic graph.
    pass


def downgrade() -> None:
    # No-op downgrade to match the restored header.
    pass
