import logging
import os
from sqlalchemy import inspect
from src.utils import db
from src.db.models import Base

# Alembic is optional at runtime; fall back to create_all if unavailable
try:
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig

    _ALEMBIC_AVAILABLE = True
except Exception:  # pragma: no cover - if alembic not installed in env
    _ALEMBIC_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _alembic_config_for_engine(engine) -> "AlembicConfig":
    """
    Build an Alembic Config pointing to the project's alembic.ini and
    attach the current SQLAlchemy URL so 'alembic' CLI settings are not required.
    """
    # Project root = parent of the 'src' directory that this file lives in
    project_root = os.path.dirname(os.path.dirname(__file__))
    ini_path = os.path.join(project_root, "alembic.ini")
    cfg = AlembicConfig(ini_path)
    # Ensure the runtime engine URL is used
    cfg.set_main_option("sqlalchemy.url", str(engine.url))
    # Some setups need this to resolve script_location if alembic.ini is minimal
    if not cfg.get_main_option("script_location"):
        cfg.set_main_option("script_location", os.path.join(project_root, "alembic"))
    return cfg


def init_db() -> None:
    """
    Initialize database schema.

    Strategy:
      - If Alembic is available AND the database already has an 'alembic_version'
        table, run migrations to 'head' (authoritative schema).
      - If Alembic is available BUT no 'alembic_version' table exists, create all
        tables from ORM metadata and then stamp the DB to 'head' so future runs
        use migrations cleanly.
      - If Alembic is not available, fall back to create_all().
    """
    engine = db.get_engine()
    inspector = inspect(engine)

    try:
        has_version_table = inspector.has_table("alembic_version")
        if _ALEMBIC_AVAILABLE:
            cfg = _alembic_config_for_engine(engine)

            if has_version_table:
                logger.info(
                    "Alembic version table found. Applying migrations to head..."
                )
                alembic_command.upgrade(cfg, "head")
                logger.info("Migrations applied successfully.")
            else:
                logger.info(
                    "No alembic_version table detected. Creating ORM tables, then stamping head..."
                )
                Base.metadata.create_all(engine)
                alembic_command.stamp(cfg, "head")
                logger.info("Schema created and stamped to head.")
        else:
            logger.warning(
                "Alembic not available. Creating ORM tables with create_all()."
            )
            Base.metadata.create_all(engine)
            logger.info("Database initialized via create_all().")

    except Exception as e:
        # Safety net: never leave the app without tables in dev/CI
        logger.exception(
            "Database initialization via Alembic failed; falling back to create_all(). Error: %s",
            e,
        )
        Base.metadata.create_all(engine)
        logger.info("Database initialized via create_all() after Alembic failure.")


if __name__ == "__main__":
    init_db()
