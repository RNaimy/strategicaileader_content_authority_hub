from src.utils import db
from sqlalchemy import text


def test_db_connection():
    with db.get_session() as session:
        result = session.execute(text("SELECT 1")).scalar()
        assert result == 1
