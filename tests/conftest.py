import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest

try:
    from src.db.session import engine, SessionLocal
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "Failed to import DB session objects. Ensure src/db/session.py defines 'engine' and 'SessionLocal'."
    ) from e


@pytest.fixture(scope="function")
def db():
    """Yield a SQLAlchemy session bound to a SAVEPOINT and roll back after each test.

    This prevents any test data from leaking into other tests or dev DBs.
    """
    connection = engine.connect()
    trans = connection.begin()
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()
