"""merge: phase8 authority_graph + phase9 improvement_recs

Revision ID: 9185cbebfb30
Revises: 3391bd7240f4, 5379fb8b2988
Create Date: 2025-09-08 17:36:43.738081

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9185cbebfb30"
down_revision: Union[str, Sequence[str], None] = ("3391bd7240f4", "5379fb8b2988")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
