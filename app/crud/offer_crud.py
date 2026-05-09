"""
Offer CRUD operations for job offers management.
"""

from datetime import datetime, timedelta
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Offer, Application, Student, Job, Company
from ..enums import RoleType, ApplicationStatus, OfferStatus, ApplicationStatusReason, OfferStatusReason
from ..datetime_utils import utc_now, to_utc_naive
from ..audit import log_audit
from ..logger import get_logger

logger = get_logger(__name__)


def _normalize_role_type(role_type) -> RoleType:
    """Return a valid RoleType from enum/string values."""
    if isinstance(role_type, RoleType):
        return role_type
    if isinstance(role_type, str):
        try:
            return RoleType(role_type)
        except ValueError:
            raise ValueError("Invalid role_type")
    return RoleType.full_time


def get_student_acceptance_state(session: Session, student_id: int) -> dict:
    """Summarize accepted offers for a student by role type."""
    statement = (
        select(Offer, Job)
        .join(Job, Offer.job_id == Job.id)
        .where(
            Offer.student_id == student_id,
            Offer.status == OfferStatus.accepted,
        )
    )
    accepted_rows = session.exec(statement).all()

    has_accepted_internship = False
    has_accepted_full_time = False
    accepted_internship_offer_ids = []

    for offer, job in accepted_rows:
        role_type = _normalize_role_type(getattr(job, "role_type", RoleType.full_time))
        if role_type == RoleType.internship:
            has_accepted_internship = True
            accepted_internship_offer_ids.append(offer.id)
        else:
            has_accepted_full_time = True

    return {
        "has_accepted_internship": has_accepted_internship,
        "has_accepted_full_time": has_accepted_full_time,
        "accepted_internship_offer_ids": accepted_internship_offer_ids,
    }


def get_application_block_reason(session: Session, student_id: int, role_type) -> Optional[str]:
    """Return the role-aware block reason for a new application or offer."""
    target_role = _normalize_role_type(role_type)
    acceptance_state = get_student_acceptance_state(session, student_id)

    if acceptance_state["has_accepted_full_time"]:
        return "Student already accepted a full-time offer and cannot apply to new jobs"
    if (
        target_role == RoleType.internship
        and acceptance_state["has_accepted_internship"]
    ):
        return "Student already accepted an internship offer and cannot apply to more internship jobs"
    return None


def _expire_overdue_offers(session: Session, student_id: Optional[int] = None) -> int:
    """
    Expire offered records past response deadline.
    Business rule: once deadline is passed, offer is treated as expired by setting:
    - offer.status = declined
    - application.status = offer_expired (revivable by company)
    """
    now = utc_now()
    statement = select(Offer).where(
        Offer.status == OfferStatus.offered,
        Offer.response_deadline != None,
        Offer.response_deadline < now,
    )
    if student_id is not None:
        statement = statement.where(Offer.student_id == student_id)

    expired_offers = session.exec(statement).all()
    if not expired_offers:
        return 0

    student_ids = {offer.student_id for offer in expired_offers}
    job_ids = {offer.job_id for offer in expired_offers}
    apps_stmt = select(Application).where(
        Application.student_id.in_(student_ids),
        Application.job_id.in_(job_ids),
    )
    applications = session.exec(apps_stmt).all()
    app_map = {(app.student_id, app.job_id): app for app in applications}

    for offer in expired_offers:
        offer.status = OfferStatus.declined
        session.add(offer)

        application = app_map.get((offer.student_id, offer.job_id))
        if application and application.status != ApplicationStatus.accepted:
            application.status = ApplicationStatus.offer_expired
            application.status_reason = ApplicationStatusReason.offer_deadline_expired
            session.add(application)

    session.commit()
    return len(expired_offers)


def create_offer(
    session: Session, 
    job_id: int, 
    student_id: int, 
    company_id: int, 
    ctc: Optional[float] = None,
    response_deadline: Optional[datetime] = None,
) -> Offer:
    """
    Create an offer for a shortlisted applicant.
    """
    # Expire older stale offers before creating or re-opening an offer.
    _expire_overdue_offers(session, student_id=student_id)

    statement = select(Application).where(
        Application.job_id == job_id, 
        Application.student_id == student_id
    )
    application = session.exec(statement).first()
    if not application:
        raise ValueError("Application not found")
    if application.status != ApplicationStatus.shortlisted:
        raise ValueError("Only shortlisted applications can be offered")
    
    # enforce CTC requirement based on job role
    job = session.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")
    if job.company_id != company_id:
        raise ValueError("Company not authorized for this job")
    if job.closed:
        raise ValueError("Cannot create offer for a closed job")
    company = session.get(Company, company_id)
    if not company or not getattr(company, "is_active", True):
        raise ValueError("Company is deactivated")
    if not getattr(company, "verified", False):
        raise ValueError("Company is not verified")

    role_type = _normalize_role_type(getattr(job, "role_type", RoleType.full_time))

    if role_type == RoleType.full_time and ctc is None:
        raise ValueError("CTC required for full-time offers")

    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        raise ValueError("Student not found")
    block_reason = get_application_block_reason(session, student_id, role_type)
    if block_reason:
        raise ValueError(block_reason.replace("apply to new jobs", "be offered new roles").replace("apply to more internship jobs", "be offered another internship role"))

    effective_deadline = response_deadline or job.application_deadline or (utc_now() + timedelta(days=7))
    effective_deadline = to_utc_naive(effective_deadline)
    if effective_deadline <= utc_now():
        raise ValueError("Offer response deadline must be in the future")

    existing_offer_stmt = select(Offer).where(
        Offer.job_id == job_id,
        Offer.student_id == student_id,
    )
    offer = session.exec(existing_offer_stmt).first()
    if offer:
        if offer.status == OfferStatus.accepted:
            raise ValueError("Accepted offer cannot be changed")
        offer.company_id = company_id
        offer.ctc = ctc
        offer.status = OfferStatus.offered
        offer.response_deadline = effective_deadline
    else:
        offer = Offer(
            job_id=job_id,
            student_id=student_id,
            company_id=company_id,
            ctc=ctc,
            status=OfferStatus.offered,
            response_deadline=effective_deadline,
        )

    application.status = ApplicationStatus.offered
    session.add(offer)
    session.add(application)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise ValueError("Unable to create offer (possible duplicate)")
    session.refresh(offer)
    return offer


def accept_offer(session: Session, offer_id: int, student_id: int) -> Optional[Offer]:
    """
    Accept an offer with database-level locking to prevent race conditions.
    
    Uses row-level locking (FOR UPDATE) to ensure only one process can accept
    an offer simultaneously, preventing double-acceptance bugs.
    """
    _expire_overdue_offers(session, student_id=student_id)

    # Lock the offer row to prevent concurrent modifications
    offer = session.exec(
        select(Offer)
        .where(Offer.id == offer_id)
        .with_for_update()  # Database row-level lock!
    ).first()
    
    if not offer:
        logger.warning(f"Offer {offer_id} not found")
        return None
    
    if offer.student_id != student_id:
        logger.warning(f"Student {student_id} unauthorized for offer {offer_id}")
        return None
    
    if offer.status != OfferStatus.offered:
        logger.info(f"Offer {offer_id} status is {offer.status}, not offered")
        return None
    
    # Verify company is still active
    company = session.get(Company, offer.company_id)
    if not company or not getattr(company, "is_active", True):
        logger.warning(f"Company {offer.company_id} not active for offer {offer_id}")
        return None
    
    # Check deadline
    if offer.response_deadline:
        now = utc_now()
        deadline = to_utc_naive(offer.response_deadline)
        if deadline <= now:
            logger.info(f"Offer {offer_id} deadline passed ({deadline} <= {now}), declining")
            offer.status = OfferStatus.declined
            offer.status_reason = OfferStatusReason.deadline_passed
            session.add(offer)
            
            app_stmt = select(Application).where(
                Application.job_id == offer.job_id,
                Application.student_id == student_id,
            )
            application = session.exec(app_stmt).first()
            if application and application.status != ApplicationStatus.accepted:
                application.status = ApplicationStatus.rejected
                application.status_reason = ApplicationStatusReason.offer_declined
                session.add(application)
            
            session.commit()
            return None
    
    # Verify student is still active
    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        logger.warning(f"Student {student_id} not active for offer {offer_id}")
        return None
    
    # Check business rules: Get job role type
    job = session.get(Job, offer.job_id)
    if not job:
        logger.warning(f"Job {offer.job_id} not found for offer {offer_id}")
        return None
    
    role_type = _normalize_role_type(getattr(job, "role_type", RoleType.full_time))
    
    # Lock and check acceptance state to prevent concurrent acceptances
    acceptance_state = get_student_acceptance_state(session, student_id)
    
    if acceptance_state["has_accepted_full_time"]:
        logger.info(f"Student {student_id} already has full-time offer")
        return None
    
    if role_type == RoleType.internship and acceptance_state["has_accepted_internship"]:
        logger.info(f"Student {student_id} already has internship offer")
        return None
    
    # ✅ NOW ACCEPT - with all checks passed and offer locked
    try:
        offer.status = OfferStatus.accepted
        offer.status_reason = OfferStatusReason.offer_accepted
        offer.updated_at = utc_now()
        student.locked_offer_id = offer.id if role_type == RoleType.full_time else None
        session.add(offer)
        session.add(student)

        # Update related application
        accepted_app_stmt = select(Application).where(
            Application.job_id == offer.job_id,
            Application.student_id == student_id,
        )
        accepted_app = session.exec(accepted_app_stmt).first()
        if accepted_app:
            accepted_app.status = ApplicationStatus.accepted
            accepted_app.status_reason = ApplicationStatusReason.offer_accepted
            accepted_app.updated_at = utc_now()
            session.add(accepted_app)

        # Decline other offers based on role type rules
        stmt = select(Offer).where(
            Offer.student_id == student_id,
            Offer.id != offer_id,
        )
        others = session.exec(stmt).all()
        other_job_ids = {o.job_id for o in others}
        other_apps_by_job_id = {}
        
        if other_job_ids:
            other_apps_stmt = select(Application).where(
                Application.student_id == student_id,
                Application.job_id.in_(other_job_ids),
            )
            other_apps = session.exec(other_apps_stmt).all()
            other_apps_by_job_id = {app.job_id: app for app in other_apps}

        for o in others:
            other_job = session.get(Job, o.job_id)
            other_role_type = _normalize_role_type(getattr(other_job, "role_type", RoleType.full_time))
            should_decline = False
            
            if o.status == OfferStatus.offered:
                should_decline = (
                    role_type == RoleType.full_time
                    or other_role_type == RoleType.internship
                )
            elif o.status == OfferStatus.accepted:
                should_decline = (
                    role_type == RoleType.full_time
                    and other_role_type == RoleType.internship
                )

            if not should_decline:
                continue

            o.status = OfferStatus.declined
            o.status_reason = OfferStatusReason.competing_offer_accepted
            o.updated_at = utc_now()
            session.add(o)
            
            other_app = other_apps_by_job_id.get(o.job_id)
            if other_app and other_app.status in {
                ApplicationStatus.offered,
                ApplicationStatus.shortlisted,
                ApplicationStatus.accepted,
            }:
                other_app.status = ApplicationStatus.declined
                other_app.status_reason = ApplicationStatusReason.offer_declined
                other_app.updated_at = utc_now()
                session.add(other_app)
        
        session.commit()
        session.refresh(offer)
        
        logger.info(f"Offer {offer_id} accepted by student {student_id}")
        log_audit(
            "offer.accepted",
            offer_id=offer.id,
            student_id=student_id,
            job_id=offer.job_id,
            company_id=offer.company_id,
        )
        return offer
        
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to accept offer {offer_id}: {str(e)}", exc_info=True)
        return None


def decline_offer(session: Session, offer_id: int, student_id: int) -> Optional[Offer]:
    """Decline an offer."""
    _expire_overdue_offers(session, student_id=student_id)

    offer = session.get(Offer, offer_id)
    if not offer or offer.student_id != student_id:
        return None
    if offer.status != OfferStatus.offered:
        return None

    offer.status = OfferStatus.declined
    session.add(offer)

    app_stmt = select(Application).where(
        Application.job_id == offer.job_id,
        Application.student_id == student_id,
    )
    application = session.exec(app_stmt).first()
    if application and application.status in {
        ApplicationStatus.offered,
        ApplicationStatus.shortlisted,
    }:
        application.status = ApplicationStatus.declined
        session.add(application)

    session.commit()
    session.refresh(offer)
    log_audit(
        "offer.declined",
        offer_id=offer.id,
        student_id=student_id,
        job_id=offer.job_id,
        company_id=offer.company_id,
    )
    return offer


def list_student_offer_summaries(
    session: Session,
    student_id: int,
    status: Optional[OfferStatus] = None,
    skip: int = 0,
    limit: int = 100,
):
    """List a student's offers with job and company context."""
    _expire_overdue_offers(session, student_id=student_id)
    statement = (
        select(Offer, Job, Company)
        .join(Job, Offer.job_id == Job.id)
        .join(Company, Offer.company_id == Company.id)
        .where(Offer.student_id == student_id)
        .order_by(Offer.created_at.desc(), Offer.id.desc())
    )
    if status is not None:
        statement = statement.where(Offer.status == status)
    statement = statement.offset(skip).limit(limit)

    rows = session.exec(statement).all()
    return [
        {
            "id": offer.id,
            "job_id": job.id,
            "company_id": company.id,
            "company_name": company.name,
            "company_active": bool(getattr(company, "is_active", True)),
            "job_title": job.title,
            "job_description": job.description,
            "role_type": job.role_type,
            "stipend": job.stipend,
            "ctc": offer.ctc if offer.ctc is not None else job.ctc,
            "ppo_available": job.ppo_available,
            "internship_duration": job.internship_duration,
            "status": offer.status,
            "status_reason": offer.status_reason,
            "response_deadline": offer.response_deadline,
            "created_at": offer.created_at,
        }
        for offer, job, company in rows
    ]


def count_student_offers(
    session: Session,
    student_id: int,
    status: Optional[OfferStatus] = None,
) -> int:
    """Count a student's offers with optional status filter."""
    _expire_overdue_offers(session, student_id=student_id)
    statement = select(func.count()).select_from(Offer).where(Offer.student_id == student_id)
    if status is not None:
        statement = statement.where(Offer.status == status)
    return session.exec(statement).one()


def list_company_accepted_offer_summaries(
    session: Session,
    company_id: int,
    skip: int = 0,
    limit: int = 100,
):
    """List accepted offers for a company with student and job context."""
    statement = (
        select(Offer, Student, Job)
        .join(Student, Offer.student_id == Student.id)
        .join(Job, Offer.job_id == Job.id)
        .where(
            Offer.company_id == company_id,
            Offer.status == OfferStatus.accepted,
        )
        .order_by(Offer.created_at.desc(), Offer.id.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return [
        {
            "id": offer.id,
            "job_id": job.id,
            "student_id": student.id,
            "student_name": student.name,
            "student_reg_no": student.reg_no,
            "reg_no": student.reg_no,
            "roll_no": student.roll_no,
            "phone": student.phone,
            "personal_email": student.personal_email,
            "address": student.address,
            "resume_url": student.resume_url,
            "github_url": student.github_url,
            "linkedin_url": student.linkedin_url,
            "leetcode_url": student.leetcode_url,
            "codeforces_url": student.codeforces_url,
            "hackerrank_url": student.hackerrank_url,
            "portfolio_url": student.portfolio_url,
            "other_coding_url": student.other_coding_url,
            "job_title": job.title,
            "job_description": job.description,
            "role_type": job.role_type,
            "stipend": job.stipend,
            "ctc": offer.ctc if offer.ctc is not None else job.ctc,
            "ppo_available": job.ppo_available,
            "internship_duration": job.internship_duration,
            "response_deadline": offer.response_deadline,
            "status": offer.status,
            "created_at": offer.created_at,
        }
        for offer, student, job in rows
    ]


def count_company_accepted_offers(session: Session, company_id: int) -> int:
    """Count accepted offers for a company."""
    statement = (
        select(func.count())
        .select_from(Offer)
        .where(
            Offer.company_id == company_id,
            Offer.status == OfferStatus.accepted,
        )
    )
    return session.exec(statement).one()


def count_offers_made(session: Session) -> int:
    """Count all valid offers made (excluding invalidated ones)."""
    statement = select(func.count()).select_from(Offer).where(Offer.status != OfferStatus.invalidated)
    return session.exec(statement).one()


def count_offers_accepted(session: Session) -> int:
    """Count all accepted offers."""
    statement = select(func.count()).select_from(Offer).where(Offer.status == OfferStatus.accepted)
    return session.exec(statement).one()


def count_offers_pending_response(session: Session) -> int:
    """Count offers awaiting student response."""
    _expire_overdue_offers(session)
    statement = select(func.count()).select_from(Offer).where(Offer.status == OfferStatus.offered)
    return session.exec(statement).one()


def list_offers_admin_summaries(session: Session, skip: int = 0, limit: int = 100):
    """List offers for admin management with student/job/company context."""
    statement = (
        select(Offer, Student, Job, Company)
        .join(Student, Offer.student_id == Student.id)
        .join(Job, Offer.job_id == Job.id)
        .join(Company, Offer.company_id == Company.id)
        .order_by(Offer.created_at.desc(), Offer.id.desc())
        .offset(skip)
        .limit(limit)
    )
    rows = session.exec(statement).all()
    return [
        {
            "id": offer.id,
            "student_id": student.id,
            "student_name": student.name,
            "company_id": company.id,
            "company_name": company.name,
            "job_id": job.id,
            "job_title": job.title,
            "job_description": job.description,
            "role_type": job.role_type,
            "ctc": offer.ctc if offer.ctc is not None else job.ctc,
            "stipend": job.stipend,
            "ppo_available": job.ppo_available,
            "internship_duration": job.internship_duration,
            "allowed_branches": job.allowed_branches,
            "response_deadline": offer.response_deadline,
            "status": offer.status,
            "created_at": offer.created_at,
        }
        for offer, student, job, company in rows
    ]


def count_offers_all(session: Session) -> int:
    """Count all offers across statuses."""
    statement = select(func.count()).select_from(Offer)
    return session.exec(statement).one()


def admin_delete_offer(session: Session, offer_id: int) -> bool:
    """
    Hard-delete an offer.
    If the offer was accepted, unlock student and reset linked application so the student is free again.
    """
    offer = session.get(Offer, offer_id)
    if not offer:
        return False

    try:
        student = session.get(Student, offer.student_id)
        if student and student.locked_offer_id == offer.id:
            student.locked_offer_id = None
            session.add(student)

        application = session.exec(
            select(Application).where(
                Application.job_id == offer.job_id,
                Application.student_id == offer.student_id,
            )
        ).first()
        if application and application.status in {ApplicationStatus.offered, ApplicationStatus.accepted}:
            application.status = ApplicationStatus.rejected
            application.status_reason = ApplicationStatusReason.manual_rejection
            session.add(application)

        session.delete(offer)
        session.commit()
        log_audit("offer.deleted_by_admin", offer_id=offer_id, student_id=offer.student_id, job_id=offer.job_id)
        return True
    except Exception:
        session.rollback()
        return False
