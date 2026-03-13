"""
Application CRUD operations for job applications management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Application, Student, Job, Offer
from ..enums import ApplicationStatus, CompanyApplicationAction, OfferStatus
from .offer_crud import create_offer, get_application_block_reason


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
    if not getattr(student, "is_active", True):
        raise ValueError("Student profile is deactivated")
    
    # CGPA eligibility
    if student.cgpa is None:
        raise ValueError("Student CGPA is missing. Ask admin to update profile.")
    if job.min_cgpa is not None and student.cgpa < job.min_cgpa:
        raise ValueError("CGPA below eligibility")
    
    # Branch eligibility
    if student.branch is None:
        raise ValueError("Student branch is missing. Ask admin to update profile.")
    if job.allowed_branches:
        allowed = [b.strip().lower() for b in job.allowed_branches.split(",") if b.strip()]
        student_branch = student.branch.value if hasattr(student.branch, "value") else str(student.branch)
        if student_branch and student_branch.lower() not in allowed:
            raise ValueError("Branch not eligible for this job")
    
    # Backlogs eligibility
    if job.max_backlogs is not None and student.backlogs is not None and student.backlogs > job.max_backlogs:
        raise ValueError("Too many backlogs to be eligible")
    
    block_reason = get_application_block_reason(
        session,
        student_id,
        getattr(job, "role_type", None),
    )
    if block_reason:
        raise ValueError(block_reason)
    
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
    """Application withdrawal is disabled by business rule."""
    return False


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
    statement = (
        select(Application)
        .order_by(Application.applied_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return session.exec(statement).all()


def count_applications(session: Session) -> int:
    """Count all applications."""
    statement = select(func.count()).select_from(Application)
    return session.exec(statement).one()


def delete_application(session: Session, application_id: int) -> Optional[bool]:
    """Delete an application (admin operation)."""
    application = session.get(Application, application_id)
    if not application:
        return None
    try:
        session.delete(application)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


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


def apply_company_action(
    session: Session,
    application: Application,
    job: Job,
    company_id: int,
    action: CompanyApplicationAction,
    ctc: Optional[float] = None,
    offer_response_deadline=None,
):
    """
    Apply a company action on an application with centralized transition rules.
    Returns either updated Application or Offer (for offered action).
    """
    if job.company_id != company_id:
        raise ValueError("Not allowed to modify this application")

    current_status = application.status
    if action == CompanyApplicationAction.offered:
        if current_status != ApplicationStatus.shortlisted:
            raise ValueError("Only shortlisted applications can be moved to offered")
        return create_offer(
            session,
            job.id,
            application.student_id,
            company_id,
            ctc,
            offer_response_deadline,
        )

    if action == CompanyApplicationAction.shortlisted:
        if current_status not in {ApplicationStatus.applied, ApplicationStatus.offered}:
            raise ValueError("Only applied/offered applications can be moved to shortlisted")
        if current_status == ApplicationStatus.offered:
            offer_stmt = select(Offer).where(
                Offer.job_id == application.job_id,
                Offer.student_id == application.student_id,
                Offer.status == OfferStatus.offered,
            )
            active_offer = session.exec(offer_stmt).first()
            if active_offer:
                active_offer.status = OfferStatus.declined
                session.add(active_offer)
        application.status = ApplicationStatus.shortlisted
    elif action == CompanyApplicationAction.rejected:
        if current_status not in {
            ApplicationStatus.applied,
            ApplicationStatus.shortlisted,
            ApplicationStatus.offered,
            ApplicationStatus.accepted,
        }:
            raise ValueError("Only active pipeline applications can be rejected")
        if current_status == ApplicationStatus.offered:
            offer_stmt = select(Offer).where(
                Offer.job_id == application.job_id,
                Offer.student_id == application.student_id,
                Offer.status == OfferStatus.offered,
            )
            active_offer = session.exec(offer_stmt).first()
            if active_offer:
                active_offer.status = OfferStatus.declined
                session.add(active_offer)

        if current_status == ApplicationStatus.accepted:
            accepted_offer_stmt = select(Offer).where(
                Offer.job_id == application.job_id,
                Offer.student_id == application.student_id,
                Offer.status == OfferStatus.accepted,
            )
            accepted_offer = session.exec(accepted_offer_stmt).first()
            if accepted_offer:
                accepted_offer.status = OfferStatus.declined
                session.add(accepted_offer)
                student = session.get(Student, application.student_id)
                if student and student.locked_offer_id == accepted_offer.id:
                    student.locked_offer_id = None
                    session.add(student)
        application.status = ApplicationStatus.rejected
    else:
        raise ValueError("Invalid status. Allowed: shortlisted, rejected, offered")

    session.add(application)
    session.commit()
    session.refresh(application)
    return application

