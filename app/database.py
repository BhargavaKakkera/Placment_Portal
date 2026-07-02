import logging
from pathlib import Path
from sqlmodel import create_engine, Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError, DatabaseError as SQLAlchemyDatabaseError
from alembic import command
from alembic.config import Config

from .config import DATABASE_URL, DB_CONNECT_TIMEOUT_SECONDS
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
)
logger.info("Database engine created")


def get_session():
    session = None
    try:
        session = Session(engine)
        logger.debug("Database session opened")
        yield session
    except Exception as e:
        logger.error(f"Error during database session: {str(e)}", exc_info=True)
        raise
    finally:
        if session:
            try:
                session.close()
                logger.debug("Database session closed")
            except Exception as e:
                logger.error(f"Error closing database session: {str(e)}", exc_info=True)


def validate_database_connection() -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection validated successfully")
    except OperationalError as e:
        logger.error(f"Database connection failed: {str(e)}", exc_info=True)
        raise DatabaseError(
            "Unable to connect to database. Verify DATABASE_URL, database existence, and credentials.",
            original_error=e
        )
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error during connection validation: {str(e)}", exc_info=True)
        raise DatabaseError("Database connection error", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error during connection validation: {str(e)}", exc_info=True)
        raise DatabaseError("Database connection error", original_error=e)


def run_migrations() -> None:
    try:
        logger.info("Starting database migrations...")
        validate_database_connection()

        project_root = Path(__file__).resolve().parent.parent
        alembic_cfg = Config(str(project_root / "alembic.ini"))
        alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except OperationalError as e:
        logger.error(f"Migration database connection error: {str(e)}", exc_info=True)
        raise DatabaseError("Migration failed - database connection error", original_error=e)
    except SQLAlchemyError as e:
        logger.error(f"Migration SQLAlchemy error: {str(e)}", exc_info=True)
        raise DatabaseError("Migration failed - database error", original_error=e)
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}", exc_info=True)
        raise DatabaseError("Migration failed", original_error=e)


def serialize_first_admin_registration(session: Session) -> None:
    """Prevent concurrent creation of the first admin account."""
    try:
        session.connection().exec_driver_sql("SELECT pg_advisory_xact_lock(424242)")
        logger.debug("Admin registration lock acquired")
    except SQLAlchemyError as e:
        logger.error(f"Failed to acquire admin registration lock: {str(e)}", exc_info=True)
        raise DatabaseError("Admin registration lock failed", original_error=e)
    except Exception as e:
        logger.error(f"Unexpected error acquiring admin lock: {str(e)}", exc_info=True)
        raise DatabaseError("Admin registration lock failed", original_error=e)

