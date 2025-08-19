

import os
from contextlib import closing
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
import pytest

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
    eng = _engine()
    with closing(eng.connect()) as conn:
        res = conn.execute(text("SELECT 1"))
        assert res.scalar() == 1


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