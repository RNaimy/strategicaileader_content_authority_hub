"""phase9: improvement_recommendations table

Revision ID: 5379fb8b2988
Revises: 77771a21927f
Create Date: 2025-09-08 16:35:43.549893

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "5379fb8b2988"
down_revision: Union[str, Sequence[str], None] = "77771a21927f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (SQLite-safe and idempotent)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if not insp.has_table("improvement_recommendations"):
        op.create_table(
            "improvement_recommendations",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("site_id", sa.Integer(), nullable=False),
            sa.Column("content_item_id", sa.Integer(), sa.ForeignKey("content_items.id"), nullable=True),
            sa.Column("flag", sa.String(length=64), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("rationale", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        )
        op.create_index(
            "ix_improve_site_flag_score",
            "improvement_recommendations",
            ["site_id", "flag", "score"],
            unique=False,
        )
    else:
        # Table already exists (previous failed migration attempt). Ensure composite index exists.
        # SQLite reflection of indexes is limited; attempt create and ignore if it already exists.
        try:
            op.create_index(
                "ix_improve_site_flag_score",
                "improvement_recommendations",
                ["site_id", "flag", "score"],
                unique=False,
            )
        except Exception:
            pass


def downgrade() -> None:
    """Downgrade schema."""
    # Best-effort drops for SQLite
    try:
        op.drop_index("ix_improve_site_flag_score", table_name="improvement_recommendations")
    except Exception:
        pass
    op.drop_table("improvement_recommendations")