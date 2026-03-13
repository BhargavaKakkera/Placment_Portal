"""
Job CRUD operations for job postings management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Job, Company, Application, Offer
from ..enums import RoleType


def create_job(session: Session, company_id: int, **data) -> Job:
    """
    Create a new job posting.
    Ensures company is verified before allowing job creation.
    """
    company = session.get(Company, company_id)
    if not company or not getattr(company, "is_active", True) or not company.verified:
        raise ValueError("Company not verified or does not exist")

    role_type = data.get("role_type", RoleType.full_time)
    if isinstance(role_type, str):
        try:
            role_type = RoleType(role_type)
        except ValueError:
            raise ValueError("Invalid role_type")
    data["role_type"] = role_type

    if role_type == RoleType.internship:
        internship_duration = data.get("internship_duration")
        if (
            internship_duration is None
            or not isinstance(internship_duration, str)
            or not internship_duration.strip()
        ):
            raise ValueError("Internship duration is required for internship roles")
        if data.get("stipend") is None:
            raise ValueError("Stipend is required for internship roles")

    if role_type == RoleType.full_time and data.get("ctc") is None:
        raise ValueError("CTC is required for full-time roles")

    allowed_branches = data.get("allowed_branches")
    if allowed_branches is not None:
        if isinstance(allowed_branches, list):
            data["allowed_branches"] = ",".join(
                [b.value if hasattr(b, "value") else str(b) for b in allowed_branches]
            )
        elif not isinstance(allowed_branches, str):
            raise ValueError("allowed_branches must be a list or comma-separated string")

    job = Job(company_id=company_id, **data)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def get_job_by_id(session: Session, job_id: int) -> Optional[Job]:
    """Get job by ID."""
    return session.get(Job, job_id)


def list_jobs(session: Session, skip: int = 0, limit: int = 100) -> List[Job]:
    """List all jobs with pagination."""
    statement = select(Job).order_by(Job.created_at.desc(), Job.id.desc()).offset(skip).limit(limit)
    return session.exec(statement).all()


def list_verified_jobs(
    session: Session, 
    skip: int = 0, 
    limit: Optional[int] = 10
) -> List[Job]:
    """
    List verified, open jobs that haven't passed the deadline.
    """
    now = datetime.utcnow()
    statement = (
        select(Job)
        .join(Company, Company.id == Job.company_id)
        .where(Company.is_active == True)
        .where(Company.verified == True)
        .where(Job.closed == False)
        .where((Job.application_deadline == None) | (Job.application_deadline >= now))
        .order_by(Job.created_at.desc(), Job.id.desc())
        .offset(skip)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return session.exec(statement).all()


def count_jobs(session: Session) -> int:
    """Count all jobs."""
    statement = select(func.count()).select_from(Job)
    return session.exec(statement).one()


def count_active_jobs(session: Session) -> int:
    """Count all active (non-closed) jobs from verified companies."""
    statement = (
        select(func.count())
        .select_from(Job)
        .join(Company, Company.id == Job.company_id)
        .where(Company.is_active == True)
        .where(Company.verified == True)
        .where(Job.closed == False)
    )
    return session.exec(statement).one()


def count_verified_jobs(session: Session) -> int:
    """Count verified, open jobs that haven't passed the deadline."""
    now = datetime.utcnow()
    statement = (
        select(func.count())
        .select_from(Job)
        .join(Company, Company.id == Job.company_id)
        .where(Company.is_active == True)
        .where(Company.verified == True)
        .where(Job.closed == False)
        .where((Job.application_deadline == None) | (Job.application_deadline >= now))
    )
    return session.exec(statement).one()


def get_applicants_for_job(session: Session, job_id: int) -> List[Application]:
    """Get all applications for a job."""
    statement = (
        select(Application)
        .where(Application.job_id == job_id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
    )
    return session.exec(statement).all()


def close_job(session: Session, job_id: int) -> Optional[Job]:
    """Close a job posting."""
    job = session.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")
    job.closed = True
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def delete_job(session: Session, job_id: int) -> Optional[bool]:
    """Delete a job posting."""
    job = session.get(Job, job_id)
    if not job:
        return None

    apps_count_stmt = select(func.count()).select_from(Application).where(Application.job_id == job_id)
    apps_count = session.exec(apps_count_stmt).one()
    offers_count_stmt = select(func.count()).select_from(Offer).where(Offer.job_id == job_id)
    offers_count = session.exec(offers_count_stmt).one()
    if apps_count > 0 or offers_count > 0:
        raise ValueError("Cannot delete job with existing applications/offers. Close the job instead.")

    try:
        session.delete(job)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None

