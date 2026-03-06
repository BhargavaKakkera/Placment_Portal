"""
Offer CRUD operations for job offers management.
"""

from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Offer, Application, Student, Job
from ..enums import RoleType, ApplicationStatus, OfferStatus


def _to_utc_naive(dt: datetime) -> datetime:
    """Normalize datetime values to UTC-naive for consistent DB comparisons."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _expire_overdue_offers(session: Session, student_id: Optional[int] = None) -> int:
    """
    Expire offered records past response deadline.
    Business rule: once deadline is passed, offer is treated as rejected by setting:
    - offer.status = declined
    - application.status = rejected
    """
    now = datetime.utcnow()
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
            application.status = ApplicationStatus.rejected
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
    if application.status == ApplicationStatus.accepted:
        raise ValueError("Accepted applications cannot be offered again")
    
    # enforce CTC requirement based on job role
    job = session.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")
    if job.company_id != company_id:
        raise ValueError("Company not authorized for this job")

    role_type = getattr(job, "role_type", RoleType.full_time)
    if isinstance(role_type, str):
        try:
            role_type = RoleType(role_type)
        except ValueError:
            raise ValueError("Invalid job role type")

    if role_type == RoleType.full_time and ctc is None:
        raise ValueError("CTC required for full-time offers")

    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        raise ValueError("Student not found")
    if student.locked_offer_id is not None:
        raise ValueError("Student already accepted another offer and cannot be offered")

    effective_deadline = response_deadline or job.application_deadline or (datetime.utcnow() + timedelta(days=7))
    effective_deadline = _to_utc_naive(effective_deadline)
    if effective_deadline <= datetime.utcnow():
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
    Accept an offer.
    - Sets this offer to accepted
    - Marks student locked
    - Declines other offers for the student
    """
    _expire_overdue_offers(session, student_id=student_id)

    # Atomic-ish: check student hasn't locked an offer and offer belongs to student.
    offer = session.get(Offer, offer_id)
    if not offer or offer.student_id != student_id:
        return None
    if offer.status != OfferStatus.offered:
        return None
    if offer.response_deadline and _to_utc_naive(offer.response_deadline) < datetime.utcnow():
        offer.status = OfferStatus.declined
        session.add(offer)
        app_stmt = select(Application).where(
            Application.job_id == offer.job_id,
            Application.student_id == student_id,
        )
        application = session.exec(app_stmt).first()
        if application and application.status != ApplicationStatus.accepted:
            application.status = ApplicationStatus.rejected
            session.add(application)
        session.commit()
        return None
    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        return None
    if student.locked_offer_id is not None:
        return None
    # student must be verified to accept offers
    if not getattr(student, 'verified', False):
        return None
    
    # perform acceptance atomically: set this offer to accepted, mark student locked,
    # and decline other offers for the student.
    try:
        offer.status = OfferStatus.accepted
        student.locked_offer_id = offer.id
        session.add(offer)
        session.add(student)

        accepted_app_stmt = select(Application).where(
            Application.job_id == offer.job_id,
            Application.student_id == student_id,
        )
        accepted_app = session.exec(accepted_app_stmt).first()
        if accepted_app:
            accepted_app.status = ApplicationStatus.accepted
            session.add(accepted_app)

        # decline other offers for this student
        stmt = select(Offer).where(
            Offer.student_id == student_id,
            Offer.id != offer_id,
            Offer.status == OfferStatus.offered,
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
            o.status = OfferStatus.declined
            session.add(o)
            other_app = other_apps_by_job_id.get(o.job_id)
            if other_app and other_app.status in {
                ApplicationStatus.offered,
                ApplicationStatus.shortlisted,
            }:
                other_app.status = ApplicationStatus.declined
                session.add(other_app)
        session.commit()
        session.refresh(offer)
        return offer
    except Exception:
        session.rollback()
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
    return offer


def get_offers_for_student(session: Session, student_id: int) -> List[Offer]:
    """Get all offers for a student."""
    _expire_overdue_offers(session, student_id=student_id)
    statement = select(Offer).where(Offer.student_id == student_id)
    return session.exec(statement).all()


def count_offers_made(session: Session) -> int:
    """Count all offers made (offered + accepted + declined)."""
    statement = select(func.count()).select_from(Offer)
    return session.exec(statement).one()


def count_offers_accepted(session: Session) -> int:
    """Count all accepted offers."""
    statement = select(func.count()).select_from(Offer).where(Offer.status == OfferStatus.accepted)
    return session.exec(statement).one()

