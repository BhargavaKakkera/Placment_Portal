"""
Offer CRUD operations for job offers management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Offer, Application, Student, Job
from ..enums import RoleType, ApplicationStatus, OfferStatus


def create_offer(
    session: Session, 
    job_id: int, 
    student_id: int, 
    company_id: int, 
    ctc: Optional[float] = None
) -> Offer:
    """
    Create an offer for a shortlisted applicant.
    """
    # Only allow offers to shortlisted applicants
    statement = select(Application).where(
        Application.job_id == job_id, 
        Application.student_id == student_id
    )
    application = session.exec(statement).first()
    if not application:
        raise ValueError("Application not found")
    if application.status != ApplicationStatus.shortlisted:
        raise ValueError("Can only make offer to shortlisted applicants")
    
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
    
    offer = Offer(job_id=job_id, student_id=student_id, company_id=company_id, ctc=ctc)
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
    # Atomic-ish: check student hasn't locked an offer and offer belongs to student.
    offer = session.get(Offer, offer_id)
    if not offer or offer.student_id != student_id:
        return None
    if offer.status != OfferStatus.offered:
        return None
    student = session.get(Student, student_id)
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
        stmt = select(Offer).where(Offer.student_id == student_id, Offer.id != offer_id)
        others = session.exec(stmt).all()
        for o in others:
            if o.status == OfferStatus.offered:
                o.status = OfferStatus.declined
                session.add(o)
                other_app_stmt = select(Application).where(
                    Application.job_id == o.job_id,
                    Application.student_id == student_id,
                )
                other_app = session.exec(other_app_stmt).first()
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

