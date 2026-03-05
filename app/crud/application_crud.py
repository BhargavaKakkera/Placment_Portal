"""
Application CRUD operations for job applications management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Application, Student, Job
from ..enums import ApplicationStatus


def apply_job(session: Session, student_id: int, job_id: int) -> Application:
    """
    Apply for a job.
    Performs eligibility checks: CGPA, branch, backlogs, deadline, etc.
    """
    job = session.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")
    if job.closed:
        raise ValueError("Job is closed")
    if job.application_deadline and job.application_deadline < datetime.utcnow():
        raise ValueError("Application deadline passed")
    
    # Check if already applied
    statement = select(Application).where(
        Application.student_id == student_id, 
        Application.job_id == job_id
    )
    exists = session.exec(statement).first()
    if exists:
        raise ValueError("Already applied to this job")
    
    student = session.get(Student, student_id)
    if not student:
        raise ValueError("Student not found")
    
    # Student must be verified by admin before applying
    if not getattr(student, 'verified', False):
        raise ValueError("Student profile not verified by admin")
    
    # CGPA eligibility
    if job.min_cgpa is not None and student.cgpa is not None and student.cgpa < job.min_cgpa:
        raise ValueError("CGPA below eligibility")
    
    # Branch eligibility
    if job.allowed_branches:
        allowed = [b.strip().lower() for b in job.allowed_branches.split(",") if b.strip()]
        student_branch = student.branch.value if hasattr(student.branch, "value") else str(student.branch)
        if student_branch and student_branch.lower() not in allowed:
            raise ValueError("Branch not eligible for this job")
    
    # Backlogs eligibility
    if job.max_backlogs is not None and student.backlogs is not None and student.backlogs > job.max_backlogs:
        raise ValueError("Too many backlogs to be eligible")
    
    # Placement rule: student who has accepted offer cannot apply
    if student.locked_offer_id is not None:
        raise ValueError("Student already accepted an offer")
    
    # Create application
    app_obj = Application(student_id=student_id, job_id=job_id)
    session.add(app_obj)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise ValueError("Already applied to this job")
    session.refresh(app_obj)
    return app_obj


def get_application_by_id(session: Session, application_id: int) -> Optional[Application]:
    """Get application by ID."""
    return session.get(Application, application_id)


def withdraw_application(
    session: Session, 
    application_id: int, 
    student_id: int
) -> Optional[bool]:
    """Withdraw an application."""
    application = session.get(Application, application_id)
    if not application or application.student_id != student_id:
        return None
    try:
        session.delete(application)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def shortlist_applicant(
    session: Session, 
    application_id: int, 
    company_id: int
) -> Optional[Application]:
    """Shortlist an applicant."""
    application = session.get(Application, application_id)
    if not application:
        raise ValueError("Application not found")
    job = session.get(Job, application.job_id)
    if not job or job.company_id != company_id:
        raise ValueError("Not allowed to update this application")
    if application.status != ApplicationStatus.applied:
        raise ValueError("Only applied applications can be shortlisted")
    application.status = ApplicationStatus.shortlisted
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def reject_applicant(
    session: Session, 
    application_id: int, 
    company_id: int
) -> Optional[Application]:
    """Reject an applicant."""
    application = session.get(Application, application_id)
    if not application:
        raise ValueError("Application not found")
    job = session.get(Job, application.job_id)
    if not job or job.company_id != company_id:
        raise ValueError("Not allowed to update this application")
    if application.status in {
        ApplicationStatus.offered,
        ApplicationStatus.accepted,
        ApplicationStatus.declined,
    }:
        raise ValueError("Cannot reject finalized applications")
    application.status = ApplicationStatus.rejected
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def list_applications(
    session: Session, 
    skip: int = 0, 
    limit: int = 100
) -> List[Application]:
    """List all applications with pagination."""
    statement = select(Application).offset(skip).limit(limit)
    return session.exec(statement).all()


def count_applications(session: Session) -> int:
    """Count all applications."""
    statement = select(func.count()).select_from(Application)
    return session.exec(statement).one()


def update_application_status(
    session: Session, 
    application_id: int, 
    status: ApplicationStatus
) -> Optional[Application]:
    """Update application status."""
    application = session.get(Application, application_id)
    if not application:
        return None
    application.status = status
    session.add(application)
    session.commit()
    session.refresh(application)
    return application

