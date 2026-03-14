from pathlib import Path
from sqlmodel import create_engine, Session
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from alembic import command
from alembic.config import Config

from .config import DATABASE_URL, DB_CONNECT_TIMEOUT_SECONDS

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
)


def get_session():
    with Session(engine) as session:
        yield session


def validate_database_connection() -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        raise RuntimeError(
            "Unable to connect to PostgreSQL. Verify DATABASE_URL, database existence, and credentials."
        ) from exc


def run_migrations() -> None:
    print("Running database migrations...")
    validate_database_connection()

    project_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    command.upgrade(alembic_cfg, "head")

    print("Database migrations complete.")


def serialize_first_admin_registration(session: Session) -> None:
    """
    Serialize the "first admin" check to avoid multiple bootstrap admins.
    """
    session.connection().exec_driver_sql("SELECT pg_advisory_xact_lock(424242)")
