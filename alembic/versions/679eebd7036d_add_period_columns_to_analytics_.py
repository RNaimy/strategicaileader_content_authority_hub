"""add period columns to analytics_snapshots

Revision ID: 679eebd7036d
Revises: 60b70c86411f
Create Date: 2025-08-31 20:24:57.290099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '679eebd7036d'
down_revision: Union[str, Sequence[str], None] = '60b70c86411f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("analytics_snapshots")}

    if "period_start" not in cols:
        op.add_column(
            "analytics_snapshots",
            sa.Column("period_start", sa.TIMESTAMP, nullable=True),
        )
    if "period_end" not in cols:
        op.add_column(
            "analytics_snapshots",
            sa.Column("period_end", sa.TIMESTAMP, nullable=True),
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("analytics_snapshots")}

    if "period_end" in cols:
        op.drop_column("analytics_snapshots", "period_end")
    if "period_start" in cols:
        op.drop_column("analytics_snapshots", "period_start")
