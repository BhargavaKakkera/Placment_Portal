from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from .database import init_db, get_session
from . import crud
from .schemas import (
    RegisterIn,
    Token,
    JobCreate,
    StudentCreate,
    CompanyCreate,
    PaginationParams,
)
from .models import User, Student, Company, Job, Application, Offer
from .auth import create_access_token, get_current_user, require_role, get_current_company, get_current_student, get_current_admin


app = FastAPI(title="Placement Portal - Placement Cell API")


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


# Jobs
@app.post("/jobs")
def create_job(job_in: JobCreate, current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    # company must be verified; crud.create_job will raise ValueError if not
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    try:
        job = crud.create_job(session, company.id, **job_in.dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return job


@app.get("/jobs")
def list_jobs(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100), session: Session = Depends(get_session)):
    jobs = crud.get_verified_jobs(session, skip=skip, limit=limit)
    return jobs


@app.post("/jobs/{job_id}/apply")
def apply_job(job_id: int, current_user: User = Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    try:
        app_obj = crud.apply_job(session, student.id, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return app_obj


# Student profile
@app.post("/students")
def create_student(student_in: StudentCreate, current_user: User = Depends(get_current_student), session: Session = Depends(get_session)):
    existing = crud.get_student_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Student profile already exists")
    student = crud.create_student(session, current_user.id, **student_in.dict())
    return student


@app.get("/students/me")
def get_my_student(current_user: User = Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return student


# Company profile
@app.post("/companies")
def create_company_endpoint(company_in: CompanyCreate, current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    existing = crud.get_company_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Company profile already exists")
    company = crud.create_company(session, current_user.id, company_in.name)
    return company


@app.get("/companies/me")
def get_my_company(current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    return company


@app.post("/companies/{company_id}/verify")
def verify_company(company_id: int, current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    try:
        verified = crud.verify_company(session, company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to verify company")
    if not verified:
        raise HTTPException(status_code=404, detail="Company not found")
    return verified


@app.get("/jobs/{job_id}/applicants")
def view_applicants(job_id: int, current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    # Ensure company owns the job
    company = crud.get_company_by_user_id(session, current_user.id)
    job = session.get(Job, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to view applicants for this job")
    applicants = crud.get_applicants_for_job(session, job_id)
    return applicants


@app.post("/applications/{application_id}/shortlist")
def shortlist(application_id: int, current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    try:
        app_obj = crud.shortlist_applicant(session, application_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return app_obj


@app.post("/applications/{application_id}/reject")
def reject(application_id: int, current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    try:
        app_obj = crud.reject_applicant(session, application_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return app_obj


@app.post("/applications/{application_id}/offers")
def make_offer(application_id: int, ctc: float = Query(...), current_user: User = Depends(get_current_company), session: Session = Depends(get_session)):
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    # ensure company owns the job
    company = crud.get_company_by_user_id(session, current_user.id)
    job = session.get(Job, application.job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not authorized for this job")
    try:
        offer = crud.create_offer(session, job.id, application.student_id, company.id, ctc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return offer


@app.post("/offers/{offer_id}/accept")
def accept_offer(offer_id: int, current_user: User = Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    offer = crud.accept_offer(session, offer_id, student.id)
    if not offer:
        raise HTTPException(status_code=400, detail="Cannot accept offer (maybe already locked or invalid)")
    return offer


@app.post("/offers/{offer_id}/decline")
def decline_offer(offer_id: int, current_user: User = Depends(get_current_student), session: Session = Depends(get_session)):
    offer = session.get(Offer, offer_id)
    student = crud.get_student_by_user_id(session, current_user.id)
    if not offer or offer.student_id != student.id:
        raise HTTPException(status_code=403, detail="Not allowed to decline this offer")
    offer.status = "declined"
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return offer


# Admin endpoints
@app.get("/admin/students")
def admin_list_students(skip: int = Query(0), limit: int = Query(100), current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    return crud.list_students(session, skip=skip, limit=limit)


@app.get("/admin/jobs")
def admin_list_jobs(skip: int = Query(0), limit: int = Query(100), current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    return crud.list_jobs(session, skip=skip, limit=limit)


@app.get("/admin/applications")
def admin_list_applications(skip: int = Query(0), limit: int = Query(100), current_user: User = Depends(get_current_admin), session: Session = Depends(get_session)):
    return crud.list_applications(session, skip=skip, limit=limit)
