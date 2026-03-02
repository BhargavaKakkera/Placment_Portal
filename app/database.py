from sqlmodel import create_engine, Session, SQLModel
from typing import Optional

DATABASE_URL = "sqlite:///./placement.db"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

def get_session():
    with Session(engine) as session:
        yield session

def init_db():
    SQLModel.metadata.create_all(engine)
