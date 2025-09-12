"""orm: add ContentLink + GraphMetric models (no-op)

Revision ID: 2a0d42b72105
Revises: 9185cbebfb30
Create Date: 2025-09-08 21:06:55.553909

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "2a0d42b72105"
down_revision: Union[str, Sequence[str], None] = "9185cbebfb30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema (SQLite-safe): only add missing content_items columns.

    This migration intentionally avoids ALTER COLUMN / constraint ops that
    SQLite can't perform in-place. It focuses on adding fields needed by the
    ORM and seed script. If future engines require type tweaks, handle them
    in a separate engine-specific migration.
    """
    # Add columns on content_items if they do not exist
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("content_items")}

    # (name, type_, kwargs)
    cols_to_add = [
        ("meta_description", sa.String(length=500), dict(nullable=True)),
        ("sod_overlap_score", sa.Float(), dict(nullable=True)),
        ("sod_density_score", sa.Float(), dict(nullable=True)),
        ("extractability_score", sa.Float(), dict(nullable=True)),
        ("chunk_count", sa.Integer(), dict(nullable=True)),
        (
            "created_at",
            sa.DateTime(timezone=True),
            dict(server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        ),
        (
            "updated_at",
            sa.DateTime(timezone=True),
            dict(server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        ),
    ]

    for name, typ, kw in cols_to_add:
        if name not in existing_cols:
            op.add_column("content_items", sa.Column(name, typ, **kw))


def downgrade() -> None:
    """Downgrade schema: drop columns added in upgrade()."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {c["name"] for c in insp.get_columns("content_items")}

    for col in [
        "updated_at",
        "created_at",
        "chunk_count",
        "extractability_score",
        "sod_density_score",
        "sod_overlap_score",
        "meta_description",
    ]:
        if col in existing_cols:
            op.drop_column("content_items", col)
