"""add content_items table

Revision ID: 53fe0cf91ebc
Revises: bdb2e742e062
Create Date: 2025-08-22 13:20:56.566116
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "53fe0cf91ebc"
down_revision: Union[str, Sequence[str], None] = "bdb2e742e062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: ensure `sites` exists, then create minimal `content_items`."""

    conn = op.get_bind()
    insp = sa.inspect(conn)

    # Create a minimal `sites` table if it's missing so the FK below can be created safely.
    # Idempotent for environments where `sites` already exists.
    if "sites" not in insp.get_table_names():
        op.create_table(
            "sites",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.UniqueConstraint("domain", name="uq_sites_domain"),
        )
        op.create_index("ix_sites_domain", "sites", ["domain"], unique=False)

    # Base content_items table (later migrations add more columns)
    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column(
            "site_id",
            sa.Integer(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.UniqueConstraint("site_id", "url", name="uq_content_site_url"),
    )
    op.create_index(
        "ix_content_items_site_id", "content_items", ["site_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_content_items_site_id", table_name="content_items")
    op.drop_table("content_items")
    # Do not drop `sites` here; it may be used by other revisions.
