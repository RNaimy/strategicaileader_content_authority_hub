from __future__ import annotations

import os
import atexit
from contextlib import contextmanager
from typing import Iterator

from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.engine import Engine


# ---------------------------------------------------------------------------
# Helper to dispose SQLAlchemy engine safely (for interpreter shutdown/reconfig)
def _dispose_current_engine() -> None:
    """Dispose the active SQLAlchemy engine if possible.
    Helps ensure DB connections are closed at interpreter shutdown or when reconfiguring.
    """
    global engine
    try:
        engine.dispose()  # type: ignore[name-defined]
    except Exception:
        # If engine isn't defined yet or already disposed, ignore.
        pass


# ---------------------------------------------------------------------------
# Unified database setup for SQLite (local) and Postgres (Supabase)
# ---------------------------------------------------------------------------
# One env var everywhere (read from real env and .env)
load_dotenv()
DEFAULT_SQLITE_URL = (
    "sqlite:///strategicaileader.db"  # keep DB in project root by default
)
DATABASE_URL: str = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
ECHO_SQL: bool = os.getenv("SQL_ECHO", "0") in {"1", "true", "True"}


def _make_engine(url: str, *, echo: bool) -> Engine:
    is_sqlite = url.startswith("sqlite")
    is_postgres = url.startswith("postgresql")

    engine_kwargs = {
        "future": True,
        "echo": echo,
        "pool_pre_ping": True,
    }
    if is_sqlite:
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    eng = create_engine(url, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[unused-ignore]
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    if is_postgres:

        @event.listens_for(eng, "connect")
        def _set_pg_timezone(dbapi_connection, connection_record):  # type: ignore[unused-ignore]
            cur = dbapi_connection.cursor()
            cur.execute("SET TIME ZONE 'UTC'")
            cur.close()

    # If SQLite file path points to a nested folder, ensure parent exists
    if is_sqlite and url.startswith("sqlite:///"):
        db_path = url.replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    return eng


engine = _make_engine(DATABASE_URL, echo=ECHO_SQL)
# Ensure all pooled connections are closed at process exit to avoid ResourceWarning
atexit.register(_dispose_current_engine)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

# Declarative base for models
Base = declarative_base()

# Expose metadata for Alembic and other tooling
get_metadata = lambda: Base.metadata


def reconfigure_database(url: str | None = None, *, echo: bool | None = None) -> None:
    """Rebuild the global engine/session using a new URL or echo flag.
    Useful for tests or switching between SQLite and Postgres.
    """
    global engine, SessionLocal, DATABASE_URL, ECHO_SQL
    if url is not None:
        DATABASE_URL = url
    if echo is not None:
        ECHO_SQL = bool(echo)
    # Close existing connections before swapping engines
    _dispose_current_engine()
    engine = _make_engine(DATABASE_URL, echo=ECHO_SQL)
    SessionLocal.configure(bind=engine)


def get_engine():
    return engine


def get_session() -> Session:
    return SessionLocal()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create tables based on Base metadata.
    Alembic should handle schema in real environments. This helper supports local bootstrap.
    """
    Base.metadata.create_all(bind=engine)


def ping() -> bool:
    """Simple connectivity check."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
