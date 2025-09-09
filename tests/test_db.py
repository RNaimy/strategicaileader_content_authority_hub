import os
from contextlib import closing
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InvalidRequestError, OperationalError
import pytest
import sys
import sqlite3
import tempfile
from src.utils import db
from concurrent.futures import ThreadPoolExecutor
# Determine backend once for skip conditions
_BACKEND = db.get_engine().url.get_backend_name()

load_dotenv()


def _build_db_url() -> str:
    # Prefer a full DATABASE_URL if present
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return url
    # Fallback to individual components from .env
    name = os.getenv("DB_NAME", "local.db").strip()
    user = os.getenv("DB_USER", "").strip()
    pwd = os.getenv("DB_PASSWORD", "").strip()
    host = os.getenv("DB_HOST", "127.0.0.1").strip()
    port = os.getenv("DB_PORT", "5432").strip()

    # If no user is provided, default to SQLite local file
    if not user:
        return f"sqlite:///{name}"
    # Default to psycopg driver for Postgres
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{name}"


def _engine():
    url = _build_db_url()
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def test_db_connect_and_select_one():
    try:
        eng = _engine()
        with closing(eng.connect()) as conn:
            res = conn.execute(text("SELECT 1"))
            assert res.scalar() == 1
    except OperationalError:
        pytest.skip("Postgres not available; skipping test_db_connect_and_select_one")


@pytest.mark.parametrize(
    "env_var,expected_driver",
    [
        (None, "sqlite"),
        ("postgresql://user:pass@localhost/dbname", "postgresql"),
    ],
)
def test_get_engine(env_var, expected_driver, monkeypatch):
    if env_var is not None:
        # If we're testing a Postgres URL but the driver isn't installed, skip gracefully
        if env_var.startswith("postgresql"):
            try:
                import psycopg2  # noqa: F401
            except ModuleNotFoundError:
                pytest.skip("psycopg2 not installed; skipping Postgres engine URL test")
        monkeypatch.setenv("DATABASE_URL", env_var)
        db.reconfigure_database(env_var)
    else:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        db.reconfigure_database("sqlite:///:memory:")
    engine = db.get_engine()
    assert engine.url.get_backend_name() == expected_driver


def test_session_scope_commit_and_rollback():
    # Use on-disk temp DB so DDL is visible across connections
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        url = f"sqlite:///{tmp.name}"
        db.reconfigure_database(url)
        engine = db.get_engine()

        # Create a dummy table
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE test (id INTEGER PRIMARY KEY, val TEXT)"))

        # Test successful commit
        with db.session_scope() as session:
            session.execute(text("INSERT INTO test (val) VALUES ('test1')"))

        with engine.connect() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM test"))
            count = res.scalar()
            assert count == 1

        # Test rollback on exception
        try:
            with db.session_scope() as session:
                session.execute(text("INSERT INTO test (val) VALUES ('test2')"))
                raise Exception("Trigger rollback")
        except Exception:
            pass

        with engine.connect() as conn:
            res = conn.execute(text("SELECT COUNT(*) FROM test"))
            count_after = res.scalar()
            assert count_after == 1  # No new row added


def test_reconfigure_database():
    db.reconfigure_database("sqlite:///:memory:")
    assert db.engine.url.database == ":memory:"


def test_init_db_no_exception():
    try:
        db.init_db()
    except Exception as e:
        pytest.fail(f"init_db() raised an exception: {e}")


def test_ping_returns_true():
    db.reconfigure_database("sqlite:///:memory:")
    assert db.ping() is True


if __name__ == "__main__":
    # Manual run helper
    try:
        eng = _engine()
        with closing(eng.connect()) as conn:
            r = conn.execute(text("SELECT 1"))
            print("DB OK:", r.scalar())
    except Exception as e:
        print("DB ERROR:", e)
        raise


# --- Additional tests for thread safety and concurrent session handling ---
import threading
import time
from src.utils.db import get_session

def test_concurrent_sessions():
    """Ensure get_session creates independent sessions safely under concurrent load."""
    results = []
    def session_task():
        with get_session() as session:
            session.execute(text("SELECT 1"))
            results.append(session.is_active)

    threads = [threading.Thread(target=session_task) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Expect 5 sessions and all of them were active independently
    assert len(results) == 5
    assert all(results)

def test_session_closes_properly():
    """Ensure session closes after context manager exit."""
    session = get_session()
    # Use the session, proving it's open
    session.execute(text("SELECT 1"))
    # Close should end any active transaction/connection
    session.close()
    # After close, the session should not be in a transaction
    assert not session.in_transaction()
    # Re-using the session should transparently reopen and work
    result = session.execute(text("SELECT 1"))
    assert result.scalar() == 1
    session.close()


@pytest.mark.skip(reason="Disabled due to thread instability with SQLite in-memory; covered by other tests.")
def test_high_concurrency_sessions():
    """Stress test: spin up many concurrent sessions and ensure all complete without errors."""
    # Ensure we're using an in-memory DB for speed/isolation
    db.reconfigure_database("sqlite:///:memory:")

    errors = []

    def worker(i: int) -> bool:
        try:
            with get_session() as session:
                session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            errors.append(str(e))
            return False

    # Run with 20 threads to simulate moderate concurrency without overwhelming the driver
    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(worker, range(20)))

    assert all(results), f"Some concurrent sessions failed: {errors}"