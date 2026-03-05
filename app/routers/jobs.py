from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from datetime import datetime
from ..database import get_session
from .. import crud
from ..schemas import JobCreate
from ..auth import get_current_company
from ..models import Job
from ..models import Application
from ..auth import get_current_student

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/", response_model=Job)
def create_job(job_in: JobCreate, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    try:
        job = crud.create_job(session, company.id, **job_in.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return job


@router.get("/")
def list_jobs(skip: int = Query(0, ge=0), limit: int = Query(10, ge=1, le=100), session: Session = Depends(get_session)):
    return crud.get_verified_jobs(session, skip=skip, limit=limit)


@router.get("/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)):
    """Get job details by ID."""
    job = crud.get_job_by_id(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/apply")
def apply_to_job(job_id: int, current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    # student applies to job
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    try:
        application = crud.apply_job(session, student.id, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return application


@router.get("/eligible")
def list_eligible_jobs(
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    jobs = crud.get_verified_jobs(session, skip=0, limit=None)

    eligible = []

    for job in jobs:

        if job.min_cgpa is not None and student.cgpa < job.min_cgpa:
            continue

        if job.max_backlogs is not None and student.backlogs > job.max_backlogs:
            continue

        if job.allowed_branches:
            branches = [b.strip() for b in job.allowed_branches.split(",") if b.strip()]
            if student.branch.value not in branches:
                continue

        if job.application_deadline and job.application_deadline < datetime.utcnow():
            continue

        if job.closed:
            continue

        eligible.append(job)

    return eligible
