import sqlite3
import os

def test_schema_tables_exist():
    # use the dev DB file created by Alembic
    assert os.path.exists("strategicaileader.db"), "strategicaileader.db not found"

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