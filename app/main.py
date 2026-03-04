from fastapi import FastAPI
from .database import init_db


app = FastAPI(title="Placement Portal - Placement Cell API")


@app.on_event("startup")
def on_startup():
    init_db()

# Include routers
from .routers import auth, jobs, students, companies, admin
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(students.router)
app.include_router(companies.router)
app.include_router(admin.router)


@app.get("/")
def root():
    return {"status": "ok"}

