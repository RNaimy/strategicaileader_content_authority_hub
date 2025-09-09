"""add source column to analytics_snapshots

Revision ID: 60b70c86411f
Revises: cf4bb1eb6eef
Create Date: 2025-08-31 20:22:43.594570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '60b70c86411f'
down_revision: Union[str, Sequence[str], None] = 'cf4bb1eb6eef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("analytics_snapshots")}
    if "source" not in cols:
        op.add_column(
            "analytics_snapshots",
            sa.Column("source", sa.String(length=30), nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("analytics_snapshots")}
    if "source" in cols:
        op.drop_column("analytics_snapshots", "source")
