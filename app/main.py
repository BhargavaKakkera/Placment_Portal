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


from .database import get_session
from .models import User
from fastapi import Depends
from sqlmodel import select


@app.get("/")
def root(session=Depends(get_session)):
    # Show all users on startup root for local/dev use
    users = session.exec(select(User)).all()
    return {"users": [ {"id": u.id, "email": u.email, "role": u.role} for u in users ]}

