"""
State transition service for managing entity lifecycle and cascading state changes.
Implements: job closure, student/company/user deactivation, and offer acceptance logic.
"""

from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Job, Application, Offer, Student, Company, User
from ..enums import (
    ApplicationStatus,
    ApplicationStatusReason,
    OfferStatus,
    OfferStatusReason,
    RoleType,
)
from ..datetime_utils import utc_now
from ..audit import log_audit


def close_job_and_cascade(session: Session, job_id: int, commit: bool = True) -> bool:
    """
    Close a job and cascade state to all related applications and offers.
    
    Lifecycle:
    - Job.closed = True, Job.closed_at = now
    - All OFFERED applications -> CLOSED_BY_JOB (reason: job_closed)
    - All active offers -> INVALIDATED (reason: job_closed)
    - Applications already ACCEPTED/DECLINED remain unchanged (offer already moved)
    
    Returns: True if successful, False if job not found/already closed
    """
    job = session.get(Job, job_id)
    if not job or job.closed:
        return False
    
    try:
        # Close the job
        job.closed = True
        job.closed_at = utc_now()
        job.updated_at = utc_now()
        session.add(job)
        
        # Find all applications for this job that are not already terminal
        apps = session.exec(
            select(Application).where(
                Application.job_id == job_id,
                Application.status.not_in([
                    ApplicationStatus.accepted,
                    ApplicationStatus.declined,
                    ApplicationStatus.closed_by_job,
                    ApplicationStatus.inactive_student,
                ])
            )
        ).all()
        
        for app in apps:
            app.status = ApplicationStatus.closed_by_job
            app.status_reason = ApplicationStatusReason.job_closed
            app.updated_at = utc_now()
            session.add(app)
        
        # Find all offers for this job that are not terminal
        offers = session.exec(
            select(Offer).where(
                Offer.job_id == job_id,
                Offer.status.not_in([
                    OfferStatus.accepted,
                    OfferStatus.declined,
                    OfferStatus.invalidated,
                ])
            )
        ).all()
        
        for offer in offers:
            offer.status = OfferStatus.invalidated
            offer.status_reason = OfferStatusReason.job_closed
            offer.updated_at = utc_now()
            session.add(offer)
        
        if commit:
            session.commit()
            log_audit("job.closed_with_cascade", job_id=job_id)
        return True
    except Exception:
        session.rollback()
        return False


def deactivate_company_and_cascade(session: Session, company_id: int) -> bool:
    """
    Deactivate company and cascade:
    - Close all company's open jobs (which cascades to applications/offers)
    - Deactivate company and its user
    
    Returns: True if successful, False if company not found/already inactive
    """
    company = session.get(Company, company_id)
    if not company or not company.is_active:
        return False
    
    try:
        # Get all open jobs for this company
        jobs = session.exec(
            select(Job).where(
                Job.company_id == company_id,
                Job.closed == False
            )
        ).all()
        
        # Close each job (which cascades internally)
        for job in jobs:
            if not close_job_and_cascade(session, job.id, commit=False):
                raise ValueError(f"Failed to close job {job.id}")
        
        # Deactivate company
        company.is_active = False
        company.deactivated_at = utc_now()
        session.add(company)
        
        # Deactivate associated user
        user = session.get(User, company.user_id)
        if user and user.is_active:
            user.is_active = False
            user.deactivated_at = utc_now()
            session.add(user)
        
        session.commit()
        for job in jobs:
            log_audit("job.closed_with_cascade", job_id=job.id)
        log_audit("company.deactivated_with_cascade", company_id=company_id)
        return True
    except Exception:
        session.rollback()
        return False


def deactivate_student_and_cascade(session: Session, student_id: int) -> bool:
    """
    Deactivate student and cascade:
    - Update all active applications -> INACTIVE_STUDENT (reason: student_deactivated)
    - Update all active offers -> INVALIDATED (reason: student_deactivated)
    - Clear locked_offer_id
    - Deactivate student and its user
    
    Returns: True if successful, False if student not found/already inactive
    """
    student = session.get(Student, student_id)
    if not student or not student.is_active:
        return False
    
    try:
        # Update all non-terminal applications
        apps = session.exec(
            select(Application).where(
                Application.student_id == student_id,
                Application.status.not_in([
                    ApplicationStatus.accepted,
                    ApplicationStatus.declined,
                    ApplicationStatus.closed_by_job,
                    ApplicationStatus.inactive_student,
                ])
            )
        ).all()
        
        for app in apps:
            app.status = ApplicationStatus.inactive_student
            app.status_reason = ApplicationStatusReason.student_deactivated
            app.updated_at = utc_now()
            session.add(app)
        
        # Update all non-terminal offers
        offers = session.exec(
            select(Offer).where(
                Offer.student_id == student_id,
                Offer.status.not_in([
                    OfferStatus.accepted,
                    OfferStatus.declined,
                    OfferStatus.invalidated,
                ])
            )
        ).all()
        
        for offer in offers:
            offer.status = OfferStatus.invalidated
            offer.status_reason = OfferStatusReason.student_deactivated
            offer.updated_at = utc_now()
            session.add(offer)
        
        # Clear locked offer
        if student.locked_offer_id:
            student.locked_offer_id = None
        
        # Deactivate student
        student.is_active = False
        student.deactivated_at = utc_now()
        session.add(student)
        
        # Deactivate associated user
        user = session.get(User, student.user_id)
        if user and user.is_active:
            user.is_active = False
            user.deactivated_at = utc_now()
            session.add(user)
        
        session.commit()
        log_audit("student.deactivated_with_cascade", student_id=student_id)
        return True
    except Exception:
        session.rollback()
        return False


def deactivate_user_and_cascade(session: Session, user_id: int) -> bool:
    """
    Deactivate user and cascade to Student/Company if they exist.
    This is the master deactivation that triggers cascading.
    
    Returns: True if successful, False if user not found/already inactive
    """
    user = session.get(User, user_id)
    if not user or not user.is_active:
        return False
    
    try:
        # Find and cascade Student
        student = session.exec(
            select(Student).where(Student.user_id == user_id)
        ).first()
        if student and student.is_active:
            deactivate_student_and_cascade(session, student.id)
        
        # Find and cascade Company
        company = session.exec(
            select(Company).where(Company.user_id == user_id)
        ).first()
        if company and company.is_active:
            deactivate_company_and_cascade(session, company.id)
        
        # Deactivate user itself (if not already done)
        user = session.get(User, user_id)
        if user.is_active:
            user.is_active = False
            user.deactivated_at = utc_now()
            session.add(user)
            session.commit()
        
        log_audit("user.deactivated_with_cascade", user_id=user_id)
        return True
    except Exception:
        session.rollback()
        return False


def accept_offer_and_cascade(session: Session, offer_id: int) -> bool:
    """
    Accept an offer with cascading logic:
    - Check offer is OFFERED (not INVALIDATED or terminal)
    - Check student is ACTIVE
    - Check job is not CLOSED
    - Mark offer as ACCEPTED
    - Invalidate competing offers for same student (based on role type)
    - Update corresponding application to ACCEPTED
    - Update student.locked_offer_id
    
    Returns: True if successful, False if checks fail
    """
    offer = session.get(Offer, offer_id)
    if not offer:
        return False
    
    # Check offer is in valid state
    if offer.status != OfferStatus.offered:
        return False
    
    # Check student is active
    student = session.get(Student, offer.student_id)
    if not student or not student.is_active:
        return False
    
    # Check job is not closed
    job = session.get(Job, offer.job_id)
    if not job or job.closed:
        return False
    
    try:
        # Accept the offer
        offer.status = OfferStatus.accepted
        offer.status_reason = OfferStatusReason.offer_accepted
        offer.updated_at = utc_now()
        session.add(offer)
        
        # Update application status
        app = session.exec(
            select(Application).where(
                Application.student_id == offer.student_id,
                Application.job_id == offer.job_id,
            )
        ).first()
        if app:
            app.status = ApplicationStatus.accepted
            app.status_reason = ApplicationStatusReason.offer_accepted
            app.updated_at = utc_now()
            session.add(app)
        
        # Update locked_offer_id
        student.locked_offer_id = offer.id
        session.add(student)
        
        # Invalidate competing offers based on job role type
        role_type = job.role_type
        competing_offers = session.exec(
            select(Offer).join(Job).where(
                Offer.student_id == offer.student_id,
                Offer.status == OfferStatus.offered,
                Offer.id != offer.id,
                Job.role_type == role_type,
            )
        ).all()
        
        for competing in competing_offers:
            competing.status = OfferStatus.invalidated
            competing.status_reason = OfferStatusReason.competing_offer_accepted
            competing.updated_at = utc_now()
            session.add(competing)
        
        session.commit()
        log_audit("offer.accepted_with_cascade", offer_id=offer_id, student_id=offer.student_id)
        return True
    except Exception:
        session.rollback()
        return False


# Query Helpers - Safe queries that respect state invariants

def get_active_applications(session: Session, student_id: int) -> List[Application]:
    """
    Get applications that are NOT closed_by_job or inactive_student.
    Safe for business logic queries.
    """
    return session.exec(
        select(Application).where(
            Application.student_id == student_id,
            Application.status.not_in([
                ApplicationStatus.closed_by_job,
                ApplicationStatus.inactive_student,
            ])
        )
    ).all()


def get_active_offers(session: Session, student_id: int) -> List[Offer]:
    """
    Get offers that are not invalidated.
    Safe for business logic queries.
    """
    return session.exec(
        select(Offer).where(
            Offer.student_id == student_id,
            Offer.status != OfferStatus.invalidated,
        )
    ).all()


def count_valid_applications(session: Session, **filters) -> int:
    """
    Count applications excluding invalid/irrelevant states.
    Used for metrics and dashboards.
    """
    stmt = select(Application).where(
        Application.status.not_in([
            ApplicationStatus.closed_by_job,
            ApplicationStatus.inactive_student,
        ])
    )
    
    if "job_id" in filters:
        stmt = stmt.where(Application.job_id == filters["job_id"])
    if "student_id" in filters:
        stmt = stmt.where(Application.student_id == filters["student_id"])
    
    return session.exec(select(func.count()).select_from(stmt.subquery())).one()


def count_valid_offers(session: Session, **filters) -> int:
    """
    Count offers excluding invalidated ones.
    Used for metrics and dashboards.
    """
    stmt = select(Offer).where(Offer.status != OfferStatus.invalidated)
    
    if "job_id" in filters:
        stmt = stmt.where(Offer.job_id == filters["job_id"])
    if "student_id" in filters:
        stmt = stmt.where(Offer.student_id == filters["student_id"])
    
    return session.exec(select(func.count()).select_from(stmt.subquery())).one()
