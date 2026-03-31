"""
Company CRUD operations for company profile management.
"""

from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Company, User, Job
from ..datetime_utils import utc_now
from ..audit import log_audit
from .state_transitions import deactivate_company_and_cascade


def create_company(session: Session, user_id: int, name: str) -> Company:
    """Create a new company profile."""
    company = Company(user_id=user_id, name=name)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def get_company_by_user_id(session: Session, user_id: int) -> Optional[Company]:
    """Get active company profile by user ID."""
    statement = select(Company).where(Company.user_id == user_id).where(Company.is_active == True)
    return session.exec(statement).first()


def get_company_by_id(session: Session, company_id: int) -> Optional[Company]:
    """Get active company profile by company ID."""
    company = session.get(Company, company_id)
    if not company or not getattr(company, "is_active", True):
        return None
    return company


def update_company(session: Session, company_id: int, **data) -> Optional[Company]:
    """Update company profile."""
    company = session.get(Company, company_id)
    if not company or not getattr(company, "is_active", True):
        return None

    for key, value in data.items():
        if hasattr(company, key):
            setattr(company, key, value)

    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def delete_company(session: Session, company_id: int) -> Optional[bool]:
    """Soft-delete company and cascade to jobs/applications/offers (state-driven)."""
    company = session.get(Company, company_id)
    if not company or not getattr(company, "is_active", True):
        return None
    return deactivate_company_and_cascade(session, company_id)


def reactivate_company(session: Session, company_id: int) -> Optional[bool]:
    """Reactivate company profile and linked user account."""
    company = session.get(Company, company_id)
    if not company:
        return None
    if getattr(company, "is_active", True):
        return True

    try:
        company.is_active = True
        company.deactivated_at = None
        session.add(company)

        user = session.get(User, company.user_id)
        if user and not getattr(user, "is_active", True):
            user.is_active = True
            user.deactivated_at = None
            session.add(user)

        session.commit()
        log_audit("company.reactivated", company_id=company_id, user_id=company.user_id)
        return True
    except Exception:
        session.rollback()
        return None


def list_companies(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    verified: bool = None,
    include_inactive: bool = False,
) -> List[Company]:
    """List companies with optional filtering."""
    statement = select(Company)
    if not include_inactive:
        statement = statement.where(Company.is_active == True)
    if verified is not None:
        statement = statement.where(Company.verified == verified)
    statement = statement.order_by(Company.name.asc(), Company.id.asc()).offset(skip).limit(limit)
    return session.exec(statement).all()


def count_companies(session: Session, verified: bool = None, include_inactive: bool = False) -> int:
    """Count companies with optional filtering."""
    statement = select(func.count()).select_from(Company)
    if not include_inactive:
        statement = statement.where(Company.is_active == True)
    if verified is not None:
        statement = statement.where(Company.verified == verified)
    return session.exec(statement).one()


def verify_company(session: Session, company_id: int) -> Optional[Company]:
    """Verify a company profile."""
    company = session.get(Company, company_id)
    if not company or not getattr(company, "is_active", True):
        return None
    company.verified = True
    session.add(company)
    session.commit()
    session.refresh(company)
    log_audit("company.verified", company_id=company_id, user_id=company.user_id)
    return company
