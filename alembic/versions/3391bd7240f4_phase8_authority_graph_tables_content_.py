"""phase8: authority graph tables (content_links, graph_metrics)

Revision ID: 3391bd7240f4
Revises: 4f08b2b289b8
Create Date: 2025-08-31 21:57:36.742162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3391bd7240f4"
down_revision: Union[str, Sequence[str], None] = "4f08b2b289b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # content_links captures outbound links from a content item. For internal links,
    # `to_content_id` references another content_items.id; for external links it is NULL
    # and the target is stored in `to_url`.
    op.create_table(
        "content_links",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("from_content_id", sa.Integer(), nullable=False),
        sa.Column("to_content_id", sa.Integer(), nullable=True),
        sa.Column("to_url", sa.String(length=2048), nullable=True),
        sa.Column("anchor_text", sa.String(length=512), nullable=True),
        sa.Column("rel", sa.String(length=64), nullable=True),  # e.g., nofollow, ugc, sponsored
        sa.Column("nofollow", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["from_content_id"], ["content_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_content_id"], ["content_items.id"], ondelete="SET NULL"),
    )

    # Helpful indexes / constraints
    op.create_index(
        "ix_content_links_from_content_id",
        "content_links",
        ["from_content_id"],
        unique=False,
    )
    op.create_index(
        "ix_content_links_to_content_id",
        "content_links",
        ["to_content_id"],
        unique=False,
    )
    # ensure we don't duplicate the same edge
    op.create_unique_constraint(
        "uq_content_links_edge",
        "content_links",
        ["from_content_id", "to_content_id", "to_url", "anchor_text"],
    )

    # graph_metrics stores per-node graph scores for quick querying
    op.create_table(
        "graph_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("degree_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("degree_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pagerank", sa.Float(), nullable=True),
        sa.Column("authority", sa.Float(), nullable=True),  # e.g., HITS authority
        sa.Column("hub", sa.Float(), nullable=True),        # e.g., HITS hub
        sa.Column("last_computed_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["content_id"], ["content_items.id"], ondelete="CASCADE"),
    )
    op.create_unique_constraint("uq_graph_metrics_content_id", "graph_metrics", ["content_id"])
    op.create_index("ix_graph_metrics_degree_in", "graph_metrics", ["degree_in"])
    op.create_index("ix_graph_metrics_degree_out", "graph_metrics", ["degree_out"])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop in reverse order to satisfy FKs
    op.drop_index("ix_graph_metrics_degree_out", table_name="graph_metrics")
    op.drop_index("ix_graph_metrics_degree_in", table_name="graph_metrics")
    op.drop_constraint("uq_graph_metrics_content_id", "graph_metrics", type_="unique")
    op.drop_table("graph_metrics")

    op.drop_constraint("uq_content_links_edge", "content_links", type_="unique")
    op.drop_index("ix_content_links_to_content_id", table_name="content_links")
    op.drop_index("ix_content_links_from_content_id", table_name="content_links")
    op.drop_table("content_links")
