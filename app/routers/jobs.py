from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from ..database import get_session
from .. import crud
from ..schemas import JobCreate, JobListOut, PaginationParams
from ..auth import get_current_company
from ..models import Job
from ..models import Application
from ..auth import get_current_student
from ..crud.offer_crud import get_application_block_reason
from ..datetime_utils import utc_now, to_utc_naive

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


@router.get("/", response_model=JobListOut)
def list_jobs(pagination: PaginationParams = Depends(), session: Session = Depends(get_session)):
    items = crud.get_verified_jobs(session, skip=pagination.skip, limit=pagination.limit)
    total = crud.count_verified_jobs(session)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.post("/{job_id}/apply")
def apply_to_job(job_id: int, current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    # student applies to job
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    try:
        application = crud.apply_job(session, student.id, job_id)
    except ValueError as e:
        message = str(e)
        if "not verified" in message or "deactivated" in message:
            raise HTTPException(status_code=403, detail=message)
        if (
            "Already applied" in message
            or "already accepted" in message
            or "cannot apply" in message
        ):
            raise HTTPException(status_code=409, detail=message)
        raise HTTPException(status_code=400, detail=message)
    return application


@router.get("/eligible")
def list_eligible_jobs(
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    if student.cgpa is None or student.branch is None:
        raise HTTPException(
            status_code=409,
            detail="Student profile is incomplete (cgpa/branch missing). Ask admin to update profile."
        )

    jobs = crud.get_verified_jobs(session, skip=0, limit=None)

    eligible = []

    for job in jobs:

        if job.min_cgpa is not None and student.cgpa < job.min_cgpa:
            continue

        if job.max_backlogs is not None and student.backlogs > job.max_backlogs:
            continue

        if job.allowed_branches:
            branches = [b.strip() for b in job.allowed_branches.split(",") if b.strip()]
            student_branch = student.branch.value if hasattr(student.branch, "value") else str(student.branch)
            if student_branch not in branches:
                continue

        if job.application_deadline and to_utc_naive(job.application_deadline) < utc_now():
            continue

        if job.closed:
            continue

        block_reason = get_application_block_reason(
            session,
            student.id,
            getattr(job, "role_type", None),
        )
        if block_reason:
            continue

        eligible.append(job)

    return eligible


@router.get("/{job_id}")
def get_job(job_id: int, session: Session = Depends(get_session)):
    """Get job details by ID."""
    job = crud.get_job_by_id(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    company = crud.get_company_by_id(session, job.company_id)
    if (
        not company
        or not getattr(company, "verified", False)
        or job.closed
        or (job.application_deadline and to_utc_naive(job.application_deadline) < utc_now())
    ):
        raise HTTPException(status_code=404, detail="Job not found")
    return job
