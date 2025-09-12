from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "3391bd7240f4"
down_revision = ("b1bb6c30e282", "c8576fa3f80f")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema with SQLite-safe guards (idempotent on re-run)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)

    existing_tables = set(insp.get_table_names())

    # -----------------------------
    # Create content_links (if missing)
    # -----------------------------
    if "content_links" not in existing_tables:
        op.create_table(
            "content_links",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("from_content_id", sa.Integer(), nullable=False),
            sa.Column("to_content_id", sa.Integer(), nullable=True),
            sa.Column("to_url", sa.String(length=2048), nullable=True),
            sa.Column("anchor_text", sa.String(length=512), nullable=True),
            sa.Column(
                "rel", sa.String(length=64), nullable=True
            ),  # e.g., nofollow, ugc, sponsored
            sa.Column(
                "nofollow",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "is_internal",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["from_content_id"], ["content_items.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["to_content_id"], ["content_items.id"], ondelete="SET NULL"
            ),
            sa.UniqueConstraint(
                "from_content_id",
                "to_content_id",
                "to_url",
                "anchor_text",
                name="uq_content_links_edge",
            ),
        )

    # Ensure indexes on content_links exist
    if "content_links" in existing_tables:
        existing_indexes = {ix["name"] for ix in insp.get_indexes("content_links")}
        if "ix_content_links_from_content_id" not in existing_indexes:
            op.create_index(
                "ix_content_links_from_content_id",
                "content_links",
                ["from_content_id"],
                unique=False,
            )
        if "ix_content_links_to_content_id" not in existing_indexes:
            op.create_index(
                "ix_content_links_to_content_id",
                "content_links",
                ["to_content_id"],
                unique=False,
            )

    # -----------------------------
    # Create graph_metrics (if missing)
    # -----------------------------
    if "graph_metrics" not in existing_tables:
        op.create_table(
            "graph_metrics",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("content_id", sa.Integer(), nullable=False),
            sa.Column("degree_in", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("degree_out", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pagerank", sa.Float(), nullable=True),
            sa.Column("authority", sa.Float(), nullable=True),  # e.g., HITS authority
            sa.Column("hub", sa.Float(), nullable=True),  # e.g., HITS hub
            sa.Column(
                "last_computed_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("extra", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(
                ["content_id"], ["content_items.id"], ondelete="CASCADE"
            ),
            sa.UniqueConstraint("content_id", name="uq_graph_metrics_content_id"),
        )

    # Ensure indexes on graph_metrics exist
    if "graph_metrics" in existing_tables:
        existing_indexes = {ix["name"] for ix in insp.get_indexes("graph_metrics")}
        if "ix_graph_metrics_degree_in" not in existing_indexes:
            op.create_index(
                "ix_graph_metrics_degree_in", "graph_metrics", ["degree_in"]
            )
        if "ix_graph_metrics_degree_out" not in existing_indexes:
            op.create_index(
                "ix_graph_metrics_degree_out", "graph_metrics", ["degree_out"]
            )


def downgrade() -> None:
    """Downgrade schema with SQLite-safe guards."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_tables = set(insp.get_table_names())

    # Drop indexes and table: graph_metrics
    if "graph_metrics" in existing_tables:
        existing_indexes = {ix["name"] for ix in insp.get_indexes("graph_metrics")}
        if "ix_graph_metrics_degree_in" in existing_indexes:
            op.drop_index("ix_graph_metrics_degree_in", table_name="graph_metrics")
        if "ix_graph_metrics_degree_out" in existing_indexes:
            op.drop_index("ix_graph_metrics_degree_out", table_name="graph_metrics")
        op.drop_table("graph_metrics")

    # Drop indexes and table: content_links
    existing_tables = set(insp.get_table_names())
    if "content_links" in existing_tables:
        existing_indexes = {ix["name"] for ix in insp.get_indexes("content_links")}
        if "ix_content_links_from_content_id" in existing_indexes:
            op.drop_index(
                "ix_content_links_from_content_id", table_name="content_links"
            )
        if "ix_content_links_to_content_id" in existing_indexes:
            op.drop_index("ix_content_links_to_content_id", table_name="content_links")
        op.drop_table("content_links")
