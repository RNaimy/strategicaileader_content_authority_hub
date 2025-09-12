"""add authority columns to content_items

Revision ID: cf4bb1eb6eef
Revises: 81d258beb4fc
Create Date: 2025-08-31 19:17:20.513529

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cf4bb1eb6eef"
down_revision: Union[str, Sequence[str], None] = "81d258beb4fc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "content_items", sa.Column("authority_entity_score", sa.Float(), nullable=True)
    )
    op.add_column(
        "content_items",
        sa.Column("authority_citation_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_items",
        sa.Column("authority_external_links", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_items",
        sa.Column("authority_schema_present", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "content_items",
        sa.Column("authority_author_bylines", sa.Integer(), nullable=True),
    )
    op.add_column(
        "content_items",
        sa.Column("authority_last_scored_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("content_items", "authority_last_scored_at")
    op.drop_column("content_items", "authority_author_bylines")
    op.drop_column("content_items", "authority_schema_present")
    op.drop_column("content_items", "authority_external_links")
    op.drop_column("content_items", "authority_citation_count")
    op.drop_column("content_items", "authority_entity_score")
