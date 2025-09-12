import sqlite3
import os
from urllib.parse import urlparse

DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
parsed = urlparse(DB_URL)
db_path = (
    parsed.path.lstrip("/") if parsed.scheme.startswith("sqlite") else "data/app.db"
)


def test_schema_tables_exist():
    # use the dev DB file created by Alembic
    assert os.path.exists(db_path), f"{db_path} not found"

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}

        # Required baseline tables
        required = {
            "alembic_version",
            "content_items",
        }
        # Optional tables that appear as phases/modules are enabled
        optional = {
            "clusters",
            "content_item_clusters",
            "keywords",
            "content_keywords",
            "internal_links",
            "gsc_metrics",
        }

        missing_required = required - tables
        assert not missing_required, f"Missing required tables: {missing_required}"

        # Soft-check optional tables; don't fail the test if they are not present yet
        missing_optional = optional - tables
        if missing_optional:
            print(
                f"[schema note] Optional tables not present yet: {sorted(missing_optional)}"
            )
    finally:
        con.close()
