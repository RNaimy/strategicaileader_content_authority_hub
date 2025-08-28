import pytest
import sqlite3
import os

@pytest.mark.skip(reason="Dev-only SQLite schema check; skip in CI")
def test_schema_tables_exist():
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("sqlite:///"):
        pytest.skip("Skipping test because DATABASE_URL is not a SQLite URL")
    if not os.path.exists("strategicaileader.db"):
        pytest.skip("Skipping test because strategicaileader.db not found")

    # use the dev DB file created by Alembic
    con = sqlite3.connect("strategicaileader.db")
    try:
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}

        expected = {
            "alembic_version",
            "clusters",
            "content_items",
            "content_item_clusters",
            "keywords",
            "content_keywords",
            "internal_links",
            "gsc_metrics",
        }
        missing = expected - tables
        assert not missing, f"Missing tables: {missing}"
    finally:
        con.close()