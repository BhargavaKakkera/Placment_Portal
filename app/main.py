from fastapi import FastAPI
from sqlmodel import Session, select

from .database import run_migrations, engine
from . import crud
from .models import User

app = FastAPI(title="Placement Portal - Placement Cell API")


@app.on_event("startup")
def on_startup() -> None:
    run_migrations()
    with Session(engine) as session:
        crud.purge_expired_unverified_users(session, older_than_days=15)


# Include routers
from .routers import auth, jobs, students, companies
from .routers.admin import router as admin_router

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(students.router)
app.include_router(companies.router)
app.include_router(admin_router)


@app.get("/")
def root():
    with Session(engine) as session:
        users = session.exec(select(User)).all()

    return {
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "password_hash": user.password_hash,
                "role": user.role,
                "created_at": user.created_at,
                "is_first_admin": user.is_first_admin,
                "verified": user.verified,
                "verified_at": user.verified_at,
                "verified_by_admin_id": user.verified_by_admin_id,
                "is_active": user.is_active,
                "deactivated_at": user.deactivated_at,
            }
            for user in users
        ]
    }
