from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy import text
from sqlalchemy import event
import os
import logging

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./placement.db")

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """Ensure SQLite enforces foreign key constraints for every connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def get_session():
    with Session(engine) as session:
        yield session


def _resolve_sqlite_file_path(database_url: str) -> str | None:
    """Resolve sqlite:/// URL into an absolute file path when applicable."""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    raw_path = database_url[len(prefix):]
    if raw_path in {":memory:", ""} or raw_path.startswith("file:"):
        return None
    return os.path.abspath(raw_path)


def _migrate_student_profile_columns():
    """Add newly introduced student profile columns for existing SQLite DBs."""
    required_columns = {
        "resume_url": "TEXT",
        "github_url": "TEXT",
        "linkedin_url": "TEXT",
        "leetcode_url": "TEXT",
        "codeforces_url": "TEXT",
        "hackerrank_url": "TEXT",
        "portfolio_url": "TEXT",
        "other_coding_url": "TEXT",
    }

    with engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(student)")).fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.execute(
                    text(f"ALTER TABLE student ADD COLUMN {column_name} {column_type}")
                )


def _migrate_user_columns():
    """Add newly introduced user columns for admin verification."""
    required_columns = {
        "is_first_admin": "INTEGER DEFAULT 0",
        "verified": "INTEGER DEFAULT 0",
        "verified_at": "TIMESTAMP",
        "verified_by_admin_id": "INTEGER",
        "is_active": "INTEGER DEFAULT 1",
        "deactivated_at": "TIMESTAMP",
    }

    with engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(user)")).fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.execute(
                    text(f"ALTER TABLE user ADD COLUMN {column_name} {column_type}")
                )


def _migrate_student_status_columns():
    """Add soft-delete/lifecycle columns to student table."""
    required_columns = {
        "is_active": "INTEGER DEFAULT 1",
        "deactivated_at": "TIMESTAMP",
    }

    with engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(student)")).fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.execute(
                    text(f"ALTER TABLE student ADD COLUMN {column_name} {column_type}")
                )


def _migrate_company_status_columns():
    """Add soft-delete/lifecycle columns to company table."""
    required_columns = {
        "is_active": "INTEGER DEFAULT 1",
        "deactivated_at": "TIMESTAMP",
    }

    with engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(company)")).fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.execute(
                    text(f"ALTER TABLE company ADD COLUMN {column_name} {column_type}")
                )


def _migrate_offer_columns():
    """Add newly introduced offer columns."""
    required_columns = {
        "response_deadline": "TIMESTAMP",
    }

    with engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(offer)")).fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.execute(
                    text(f"ALTER TABLE offer ADD COLUMN {column_name} {column_type}")
                )


def _ensure_indexes():
    """Create frequently-used indexes if they do not already exist."""
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_user_role ON user(role)",
        "CREATE INDEX IF NOT EXISTS ix_user_verified ON user(verified)",
        "CREATE INDEX IF NOT EXISTS ix_user_is_active ON user(is_active)",
        "CREATE INDEX IF NOT EXISTS ix_student_verified ON student(verified)",
        "CREATE INDEX IF NOT EXISTS ix_student_is_active ON student(is_active)",
        "CREATE INDEX IF NOT EXISTS ix_company_verified ON company(verified)",
        "CREATE INDEX IF NOT EXISTS ix_company_is_active ON company(is_active)",
        "CREATE INDEX IF NOT EXISTS ix_job_company_id ON job(company_id)",
        "CREATE INDEX IF NOT EXISTS ix_job_role_type ON job(role_type)",
        "CREATE INDEX IF NOT EXISTS ix_job_closed ON job(closed)",
        "CREATE INDEX IF NOT EXISTS ix_job_application_deadline ON job(application_deadline)",
        "CREATE INDEX IF NOT EXISTS ix_application_student_id ON application(student_id)",
        "CREATE INDEX IF NOT EXISTS ix_application_job_id ON application(job_id)",
        "CREATE INDEX IF NOT EXISTS ix_application_status ON application(status)",
        "CREATE INDEX IF NOT EXISTS ix_offer_job_id ON offer(job_id)",
        "CREATE INDEX IF NOT EXISTS ix_offer_student_id ON offer(student_id)",
        "CREATE INDEX IF NOT EXISTS ix_offer_company_id ON offer(company_id)",
        "CREATE INDEX IF NOT EXISTS ix_offer_status ON offer(status)",
        "CREATE INDEX IF NOT EXISTS ix_offer_response_deadline ON offer(response_deadline)",
    ]

    with engine.begin() as conn:
        for stmt in index_statements:
            conn.execute(text(stmt))


def init_db():
    """Initialize database.

    In development, set the environment variable `RESET_DB=1` before starting
    the app to remove the existing SQLite file and recreate tables. This is
    useful when models have changed and you don't have migrations configured.

    WARNING: this deletes `placement.db` when `RESET_DB` is set.
    For production use proper migrations (alembic) instead of this.
    """
    reset = os.getenv("RESET_DB")
    db_file = _resolve_sqlite_file_path(DATABASE_URL) or os.path.join(os.getcwd(), "placement.db")
    if reset and os.path.exists(db_file):
        logging.warning("RESET_DB is set - removing existing SQLite DB file and recreating schema")
        try:
            os.remove(db_file)
        except PermissionError:
            # Common on Windows when a pooled SQLite connection is still open.
            try:
                engine.dispose()
                os.remove(db_file)
            except Exception:
                logging.exception("Failed to remove existing DB file")
        except Exception:
            logging.exception("Failed to remove existing DB file")
    SQLModel.metadata.create_all(engine)
    _migrate_student_profile_columns()
    _migrate_user_columns()
    _migrate_student_status_columns()
    _migrate_company_status_columns()
    _migrate_offer_columns()
    _ensure_indexes()
