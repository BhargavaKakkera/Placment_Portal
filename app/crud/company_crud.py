"""
Company CRUD operations for company profile management.
"""

from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Company


def create_company(session: Session, user_id: int, name: str) -> Company:
    """Create a new company profile."""
    company = Company(user_id=user_id, name=name)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def get_company_by_user_id(session: Session, user_id: int) -> Optional[Company]:
    """Get company profile by user ID."""
    statement = select(Company).where(Company.user_id == user_id)
    return session.exec(statement).first()


def get_company_by_id(session: Session, company_id: int) -> Optional[Company]:
    """Get company profile by company ID."""
    return session.get(Company, company_id)


def update_company(session: Session, company_id: int, **data) -> Optional[Company]:
    """Update company profile."""
    company = session.get(Company, company_id)
    if not company:
        return None
    
    for key, value in data.items():
        if hasattr(company, key):
            setattr(company, key, value)
    
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def delete_company(session: Session, company_id: int) -> Optional[bool]:
    """Delete company profile."""
    company = session.get(Company, company_id)
    if not company:
        return None
    try:
        session.delete(company)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def list_companies(
    session: Session, 
    skip: int = 0, 
    limit: int = 100, 
    verified: bool = None
) -> List[Company]:
    """List companies with optional filtering."""
    statement = select(Company)
    if verified is not None:
        statement = statement.where(Company.verified == verified)
    statement = statement.offset(skip).limit(limit)
    return session.exec(statement).all()


def count_companies(session: Session, verified: bool = None) -> int:
    """Count companies with optional filtering."""
    statement = select(func.count()).select_from(Company)
    if verified is not None:
        statement = statement.where(Company.verified == verified)
    return session.exec(statement).one()


def verify_company(session: Session, company_id: int) -> Optional[Company]:
    """Verify a company profile."""
    company = session.get(Company, company_id)
    if not company:
        return None
    company.verified = True
    session.add(company)
    session.commit()
    session.refresh(company)
    return company

