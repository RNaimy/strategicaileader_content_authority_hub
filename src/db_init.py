import logging
from src.utils import db
from src.db.models import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db() -> None:
    """Initialize database schema by creating all tables from SQLAlchemy metadata.

    Raises
    ------
    Exception
        Re-raises any exception after logging to make failures visible to callers/CI.
    """
    try:
        engine = db.get_engine()
        logger.info("Creating database tables (if not exist)...")
        Base.metadata.create_all(engine)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

if __name__ == "__main__":
    init_db()