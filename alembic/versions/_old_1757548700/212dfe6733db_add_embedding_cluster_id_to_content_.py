"""add embedding+cluster_id to content_items

Revision ID: 212dfe6733db
Revises: eac32663f359
Create Date: 2025-08-24 13:35:58.647006
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "212dfe6733db"
down_revision: Union[str, Sequence[str], None] = "eac32663f359"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table_name: str, column_name: str) -> bool:
    """Return True if a column exists on the given table."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table_name)]
    return column_name in cols


def upgrade() -> None:
    """Upgrade schema: add nullable embedding + cluster_id columns if missing.

    This migration is SQLite-safe (uses inspection + batch mode) and
    intentionally **does not** drop or alter unrelated tables/constraints.
    """
    with op.batch_alter_table("content_items") as batch:
        if not column_exists("content_items", "embedding"):
            batch.add_column(sa.Column("embedding", sa.JSON(), nullable=True))
        if not column_exists("content_items", "cluster_id"):
            batch.add_column(sa.Column("cluster_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema: drop columns if present.

    Note: SQLite also requires batch mode for column drops.
    """
    with op.batch_alter_table("content_items") as batch:
        if column_exists("content_items", "cluster_id"):
            batch.drop_column("cluster_id")
        if column_exists("content_items", "embedding"):
            batch.drop_column("embedding")
