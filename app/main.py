from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from .database import init_db, get_session
from . import crud
from .schemas import RegisterIn, Token, JobCreate, StudentCreate, CompanyCreate
from .models import User, Student, Company, Job, Application, Offer
from .auth import create_access_token, get_current_user

app = FastAPI(title="Placement Portal - Minimal")


@app.on_event("startup")
def on_startup():
    init_db()


@app.post("/auth/register", response_model=Token)
def register(payload: RegisterIn, session: Session = Depends(get_session)):
    existing = session.exec(select(User).where(User.email == payload.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = crud.create_user(session, payload.email, payload.password, payload.role)
    token = create_access_token({"user_id": user.id, "role": user.role})
    return {"access_token": token}


@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = crud.authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    token = create_access_token({"user_id": user.id, "role": user.role})
    return {"access_token": token}


@app.post("/jobs")
def create_job(job_in: JobCreate, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "company":
        raise HTTPException(status_code=403, detail="Only companies can post jobs")
    # find company
    company = session.exec(select(Company).where(Company.user_id == current_user.id)).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    job = crud.create_job(session, company.id, **job_in.dict())
    return job


@app.get("/jobs")
def list_jobs(session: Session = Depends(get_session)):
    return session.exec(select(Job)).all()


@app.post("/jobs/{job_id}/apply")
def apply_job(job_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can apply")
    student = session.exec(select(Student).where(Student.user_id == current_user.id)).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    app_obj = crud.apply_job(session, student.id, job_id)
    return app_obj


@app.post("/students")
def create_student(student_in: StudentCreate, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only users with role 'student' can create student profiles")
    existing = crud.get_student_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Student profile already exists")
    student = crud.create_student(session, current_user.id, **student_in.dict())
    return student


@app.get("/students/me")
def get_my_student(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students have student profiles")
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return student


@app.post("/companies")
def create_company_endpoint(company_in: CompanyCreate, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "company":
        raise HTTPException(status_code=403, detail="Only users with role 'company' can create company profiles")
    existing = crud.get_company_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Company profile already exists")
    company = crud.create_company(session, current_user.id, company_in.name)
    return company


@app.get("/companies/me")


@app.post("/companies/{company_id}/verify")
def verify_company(company_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can verify companies")
    company = session.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    verified = crud.verify_company(session, company_id)
    return verified
def get_my_company(current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "company":
        raise HTTPException(status_code=403, detail="Only companies have company profiles")
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    return company


@app.post("/applications/{app_id}/offers")
def make_offer(app_id: int, ctc: float, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "company":
        raise HTTPException(status_code=403, detail="Only companies can make offers")
    application = session.get(Application, app_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    # find company
    company = session.exec(select(Company).where(Company.user_id == current_user.id)).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    offer = crud.create_offer(session, application.job_id, application.student_id, company.id, ctc)
    return offer


@app.post("/offers/{offer_id}/accept")
def accept_offer(offer_id: int, current_user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if current_user.role != "student":
        raise HTTPException(status_code=403, detail="Only students can accept offers")
    student = session.exec(select(Student).where(Student.user_id == current_user.id)).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    offer = crud.accept_offer(session, offer_id, student.id)
    if not offer:
        raise HTTPException(status_code=400, detail="Cannot accept offer (maybe already locked or invalid)")
    return offer
