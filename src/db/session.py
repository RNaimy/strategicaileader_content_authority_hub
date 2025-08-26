

"""Database session and engine setup.

This module provides:
- SQLAlchemy Engine configured from DATABASE_URL (defaults to SQLite ./data/app.db)
- SessionLocal factory
- init_db() to create tables and ensure SQLite folders/PRAGMAs
- get_db() FastAPI-style dependency generator
"""
from __future__ import annotations

import os
import pathlib
import logging
import sys
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

 # Ensure project root is importable as a package (helps when running ad-hoc scripts)
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Base where all models are registered (support both old and new locations)
try:
    from src.db.models import Base  # preferred location
except ModuleNotFoundError:  # fallback if models live at src/models.py (legacy)
    from src.models import Base  # type: ignore

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Ensure directory exists for SQLite file paths like sqlite:///./data/app.db
if IS_SQLITE:
    db_path = DATABASE_URL.replace("sqlite:///", "")
    db_dir = pathlib.Path(db_path).expanduser().resolve().parent
    db_dir.mkdir(parents=True, exist_ok=True)

# Create engine with reasonable defaults
engine = create_engine(
    DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
)

# Apply useful SQLite PRAGMAs for concurrency & integrity
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # type: ignore[override]
    if not IS_SQLITE:
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


# --------------------------------------------------------------------------------------
# Compatibility shim: expose a `database` object (async-friendly) for old code paths
# that expect `from src.db.session import database`. If `databases` package is
# available, use it against the configured DATABASE_URL; otherwise provide a minimal
# async shim that executes via SQLAlchemy engine. This keeps sync-first design while
# preserving API compatibility for routers that expect `.connect()` / `.disconnect()`
# and `.execute()` methods.
try:
    from databases import Database  # type: ignore
    _HAS_DATABASES = True
except Exception:
    _HAS_DATABASES = False

if _HAS_DATABASES:
    database = Database(DATABASE_URL)
else:
    from sqlalchemy import text as _sql_text

    class _SyncDatabaseShim:
        def __init__(self, _engine: Engine):
            self._engine = _engine
            self._connected = False

        async def connect(self) -> None:  # no-op for sync engine
            self._connected = True

        async def disconnect(self) -> None:  # no-op for sync engine
            self._connected = False

        async def execute(self, query, values=None):
            # Accept raw SQL string or SQLAlchemy TextClause
            stmt = query if hasattr(query, "compile") else _sql_text(str(query))
            with self._engine.begin() as conn:
                result = conn.execute(stmt, values or {})
                # Return rowcount if available to mimic `databases` behavior
                return getattr(result, "rowcount", None)

        async def fetch_one(self, query, values=None):
            stmt = query if hasattr(query, "compile") else _sql_text(str(query))
            with self._engine.connect() as conn:
                res = conn.execute(stmt, values or {})
                row = res.mappings().first()
                return dict(row) if row else None

        async def fetch_all(self, query, values=None):
            stmt = query if hasattr(query, "compile") else _sql_text(str(query))
            with self._engine.connect() as conn:
                res = conn.execute(stmt, values or {})
                return [dict(r) for r in res.mappings().all()]

    database = _SyncDatabaseShim(engine)


# Session factory
__all__ = [
    "engine",
    "SessionLocal",
    "init_db",
    "get_db",
    "get_session",
    "session_scope",
    "ping_db",
    "database",
]
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create database tables if they don't exist."""
    if IS_SQLITE:
        # Re-check directory in case env changed at runtime
        db_path = DATABASE_URL.replace("sqlite:///", "")
        pathlib.Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized: %s", DATABASE_URL)


def get_db() -> Generator:
    """Yield a SQLAlchemy session and ensure close afterwards (FastAPI dependency)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper for getting a session (non-generator)
def get_session():
    """Return a new SQLAlchemy session (non-generator)."""
    return SessionLocal()


# Optional context manager for scripts/tests
@contextmanager
def session_scope() -> Generator:
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


def ping_db() -> bool:
    """Lightweight connectivity check (SELECT 1). Returns True if OK, False otherwise."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("DB ping failed")
        return False