"""ensure captured_at on analytics_snapshots

Revision ID: 10a09e43ece5
Revises: 8ea2ec68c1d2
Create Date: 2025-08-31 20:42:14.801669

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "10a09e43ece5"
down_revision: Union[str, Sequence[str], None] = "8ea2ec68c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_columns(table_name: str) -> set[str]:
    """Return a set of existing column names for the given table.

    Works on SQLite as well as other DBs by falling back to PRAGMA when needed.
    """
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    cols: set[str] = set()
    if dialect_name == "sqlite":
        res = bind.execute(text('PRAGMA table_info("%s")' % table_name))
        cols = {row[1] for row in res}
    else:
        insp = sa.inspect(bind)
        for col in insp.get_columns(table_name):
            cols.add(col["name"]) if isinstance(col, dict) else cols.add(col.name)
    return cols


def upgrade() -> None:
    """Upgrade schema: ensure `captured_at` and `updated_at` exist.

    Both are non-null with CURRENT_TIMESTAMP defaults to satisfy inserts that
    RETURN these columns immediately.
    """
    existing = _table_columns("analytics_snapshots")

    # We use batch_alter_table for broad compatibility with SQLite
    with op.batch_alter_table("analytics_snapshots", schema=None) as batch:
        if "captured_at" not in existing:
            batch.add_column(
                sa.Column(
                    "captured_at",
                    sa.DateTime(),
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                    nullable=False,
                )
            )
        if "updated_at" not in existing:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(),
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                    nullable=False,
                )
            )

    # Clear server_default so future migrations match model definitions (optional)
    # Only do this on dialects that support ALTER COLUMN
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        with op.batch_alter_table("analytics_snapshots", schema=None) as batch:
            if "captured_at" not in existing:
                batch.alter_column("captured_at", server_default=None)
            if "updated_at" not in existing:
                batch.alter_column("updated_at", server_default=None)


def downgrade() -> None:
    """Downgrade schema: drop columns if they exist."""
    existing = _table_columns("analytics_snapshots")
    with op.batch_alter_table("analytics_snapshots", schema=None) as batch:
        if "updated_at" in existing:
            batch.drop_column("updated_at")
        if "captured_at" in existing:
            batch.drop_column("captured_at")
