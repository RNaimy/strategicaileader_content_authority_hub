"""add analytics_snapshots table

Revision ID: ce01e106f155
Revises: 77771a21927f
Create Date: 2025-08-27 12:31:35.338641

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ce01e106f155"
down_revision: Union[str, Sequence[str], None] = "77771a21927f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Integer(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("period_start", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("period_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source_row_count", sa.Integer(), nullable=True),
        sa.Column("content_items_count", sa.Integer(), nullable=True),
        sa.Column("pages_indexed", sa.Integer(), nullable=True),
        sa.Column("indexed_pct", sa.Float(), nullable=True),
        sa.Column("average_position", sa.Float(), nullable=True),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("clicks", sa.Integer(), nullable=True),
        sa.Column("impressions", sa.Integer(), nullable=True),
        sa.Column("organic_sessions", sa.Integer(), nullable=True),
        sa.Column("conversions", sa.Integer(), nullable=True),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("notes", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "site_id", "captured_at", "source", name="uq_snapshot_site_capture_source"
        ),
    )
    op.create_index(
        "ix_analytics_snapshots_site_id", "analytics_snapshots", ["site_id"]
    )
    op.create_index(
        "ix_analytics_snapshots_captured_at", "analytics_snapshots", ["captured_at"]
    )
    op.create_index("ix_analytics_snapshots_source", "analytics_snapshots", ["source"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_analytics_snapshots_source", table_name="analytics_snapshots")
    op.drop_index(
        "ix_analytics_snapshots_captured_at", table_name="analytics_snapshots"
    )
    op.drop_index("ix_analytics_snapshots_site_id", table_name="analytics_snapshots")
    op.drop_table("analytics_snapshots")
