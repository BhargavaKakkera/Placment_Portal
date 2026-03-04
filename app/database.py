from sqlmodel import create_engine, Session, SQLModel
from sqlalchemy import text
import os
import logging

DATABASE_URL = "sqlite:///./placement.db"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})


def get_session():
    with Session(engine) as session:
        yield session


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


def init_db():
    """Initialize database.

    In development, set the environment variable `RESET_DB=1` before starting
    the app to remove the existing SQLite file and recreate tables. This is
    useful when models have changed and you don't have migrations configured.

    WARNING: this deletes `placement.db` when `RESET_DB` is set.
    For production use proper migrations (alembic) instead of this.
    """
    reset = os.getenv("RESET_DB")
    db_file = os.path.join(os.getcwd(), "placement.db")
    if reset and os.path.exists(db_file):
        logging.warning("RESET_DB is set - removing existing placement.db and recreating schema")
        try:
            os.remove(db_file)
        except Exception:
            logging.exception("Failed to remove existing DB file")
    SQLModel.metadata.create_all(engine)
    _migrate_student_profile_columns()
