"""add metrics columns to analytics_snapshots

Revision ID: 8ea2ec68c1d2
Revises: 679eebd7036d
Create Date: 2025-08-31 20:33:22.588078

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ea2ec68c1d2'
down_revision: Union[str, Sequence[str], None] = '679eebd7036d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema by adding missing metrics columns (idempotent)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("analytics_snapshots")}

    # Define columns we want to ensure exist: mapping of name -> SQLAlchemy Column
    desired = {
        "captured_at": sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        "source_row_count": sa.Column("source_row_count", sa.Integer(), nullable=True),
        "content_items_count": sa.Column("content_items_count", sa.Integer(), nullable=True),
        "pages_indexed": sa.Column("pages_indexed", sa.Integer(), nullable=True),
        "indexed_pct": sa.Column("indexed_pct", sa.Float(), nullable=True),
        "average_position": sa.Column("average_position", sa.Float(), nullable=True),
        "ctr": sa.Column("ctr", sa.Float(), nullable=True),
        "clicks": sa.Column("clicks", sa.Integer(), nullable=True),
        "impressions": sa.Column("impressions", sa.Integer(), nullable=True),
        "organic_sessions": sa.Column("organic_sessions", sa.Integer(), nullable=True),
        "conversions": sa.Column("conversions", sa.Integer(), nullable=True),
        "revenue": sa.Column("revenue", sa.Numeric(12, 2), nullable=True),
        "notes": sa.Column("notes", sa.JSON(), nullable=True),
    }

    # Only add columns that are not already present
    to_add = [col for name, col in desired.items() if name not in existing_cols]

    if not to_add:
        return

    with op.batch_alter_table("analytics_snapshots", schema=None) as batch:
        for col in to_add:
            batch.add_column(col)


def downgrade() -> None:
    """Downgrade schema by dropping metrics columns if present (idempotent)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("analytics_snapshots")}

    to_drop = [
        "captured_at",
        "notes",
        "revenue",
        "conversions",
        "organic_sessions",
        "impressions",
        "clicks",
        "ctr",
        "average_position",
        "indexed_pct",
        "pages_indexed",
        "content_items_count",
        "source_row_count",
    ]

    with op.batch_alter_table("analytics_snapshots", schema=None) as batch:
        for name in to_drop:
            if name in existing_cols:
                batch.drop_column(name)
