"""init schema

Revision ID: 90816bc247c2
Revises:
Create Date: 2025-08-19 17:17:03.132148

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "90816bc247c2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to initial baseline for StrategicAILeader Content Authority Hub."""
    # clusters
    op.create_table(
        "clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "code", sa.String(length=32), nullable=False, unique=True, index=True
        ),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # content items
    op.create_table(
        "content_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "slug", sa.String(length=255), nullable=False, unique=True, index=True
        ),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=True, unique=True),
        sa.Column("publish_date", sa.DateTime(), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True, index=True),
        sa.Column("pillar", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("primary_keyword", sa.String(length=255), nullable=True),
        sa.Column("secondary_keywords", sa.Text(), nullable=True),
        sa.Column(
            "topic_authority_score", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    # association: content_items <-> clusters (many-to-many)
    op.create_table(
        "content_item_clusters",
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["content_id"], ["content_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["cluster_id"], ["clusters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_id", "cluster_id"),
    )

    # keywords
    op.create_table(
        "keywords",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "keyword", sa.String(length=255), nullable=False, unique=True, index=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    # association: content_items <-> keywords (many-to-many) with weight
    op.create_table(
        "content_keywords",
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("keyword_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["content_id"], ["content_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("content_id", "keyword_id"),
    )

    # internal links between content items
    op.create_table(
        "internal_links",
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("anchor_text", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_id"], ["content_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_id"], ["content_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("source_id", "target_id"),
    )

    # Google Search Console daily metrics per content item
    op.create_table(
        "gsc_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float(), nullable=True),
        sa.Column("position", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["content_id"], ["content_items.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("content_id", "date", name="uq_gsc_content_date"),
    )

    # helpful indexes (SQLite-safe)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_content_items_publish_date ON content_items (publish_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_content_items_category ON content_items (category)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_internal_links_source ON internal_links (source_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_internal_links_target ON internal_links (target_id)"
    )


def downgrade() -> None:
    """Drop all objects created in upgrade in reverse dependency order.
    Use IF EXISTS for SQLite-safe drops to tolerate partial/failed upgrades.
    """
    # Association tables first (depend on parents)
    op.execute("DROP TABLE IF EXISTS content_keywords")
    op.execute("DROP TABLE IF EXISTS content_item_clusters")

    # Tables that depend on content_items
    op.execute("DROP INDEX IF EXISTS ix_internal_links_source")
    op.execute("DROP INDEX IF EXISTS ix_internal_links_target")
    op.execute("DROP TABLE IF EXISTS internal_links")

    # Other standalone tables
    op.execute("DROP TABLE IF EXISTS gsc_metrics")

    # Drop indexes on content_items before dropping the table
    op.execute("DROP INDEX IF EXISTS ix_content_items_publish_date")
    op.execute("DROP INDEX IF EXISTS ix_content_items_category")

    # Core parent tables last
    op.execute("DROP TABLE IF EXISTS content_items")
    op.execute("DROP TABLE IF EXISTS keywords")
    op.execute("DROP TABLE IF EXISTS clusters")
