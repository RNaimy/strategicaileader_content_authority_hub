"""baseline after cleanup

Revision ID: bb4b105c05bd
Revises:
Create Date: 2025-09-10 18:31:27.827414

This is a squashed baseline created after removing/cycling older revisions.
It intentionally performs no DDL because the live SQLite schema is already in the desired state.
Use `alembic stamp bb4b105c05bd` to align the alembic_version table with this baseline.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bb4b105c05bd"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

replaces: Union[str, Sequence[str], None] = (
    "10a09e43ece5",
    "212dfe6733db",
    "2a0d42b72105",
    "3391bd7240f4",
    "5379fb8b2988",
    "60b70c86411f",
    "679eebd7036d",
    "77771a21927f",
    "81d258beb4fc",
    "8ea2ec68c1d2",
    "9185cbebfb30",
    "a1878f49b688",
    "b1bb6c30e282",
    "c83bddaeb395",
    "c8576fa3f80f",
    "cd3e89114a5c",
    "ce01e106f155",
    "cf4bb1eb6eef",
    "eac32663f359",
)


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
