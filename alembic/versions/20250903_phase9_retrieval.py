"""phase9: retrieval embeddings + FTS/tsvector

Revision ID: 20250903_phase9_retrieval
Revises: 4f08b2b289b8
Create Date: 2025-09-03

"""
from alembic import op
import sqlalchemy as sa

revision = "20250903_phase9_retrieval"
down_revision = "4f08b2b289b8"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "content_item_embeddings",
        sa.Column("content_id", sa.Integer, primary_key=True),
        sa.Column("embedding", sa.LargeBinary, nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
    )

    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE IF NOT EXISTS content_items_fts "
            "USING fts5(content_id UNINDEXED, title, body)"
        )

def downgrade() -> None:
    op.drop_table("content_item_embeddings")

    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql("DROP TABLE IF EXISTS content_items_fts")
