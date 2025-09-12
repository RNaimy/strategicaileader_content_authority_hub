"""phase10: add extractability to SODMetric (SQLite-safe)

Revision ID: c83bddaeb395
Revises: None
Create Date: 2025-09-09 09:50:04.625959
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c83bddaeb395"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add `extractability` column to `sod_metrics` in a SQLite-safe way.
    Uses batch_alter_table to support SQLite which lacks direct ALTER support.
    """
    with op.batch_alter_table("sod_metrics") as batch_op:
        batch_op.add_column(sa.Column("extractability", sa.Float(), nullable=True))

    # If you want an index, uncomment below:
    # op.create_index("ix_sod_metrics_extractability", "sod_metrics", ["extractability"])


def downgrade() -> None:
    """
    Remove `extractability` column from `sod_metrics` in a SQLite-safe way.
    """
    # If you created an index in upgrade, drop it first:
    # op.drop_index("ix_sod_metrics_extractability", table_name="sod_metrics")

    with op.batch_alter_table("sod_metrics") as batch_op:
        batch_op.drop_column("extractability")
