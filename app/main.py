from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .database import run_migrations, engine
from . import crud
from .config import SECRET_KEY

app = FastAPI(title="Placement Portal - Placement Cell API")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    run_migrations()
    with Session(engine) as session:
        crud.purge_expired_unverified_users(session, older_than_days=15)


# Include routers
from .routers import auth, jobs, students, companies
from .routers.admin import router as admin_router
from .ui import router as ui_router

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(students.router)
app.include_router(companies.router)
app.include_router(admin_router)
app.include_router(ui_router)


@app.get("/")
def root():
    return RedirectResponse(url="/ui/", status_code=307)
