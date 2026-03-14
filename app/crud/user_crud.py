"""
User CRUD operations for authentication and admin management.
"""

from datetime import timedelta
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import User, Student, Company, Application, Offer, Job
from ..auth import hash_password, verify_password
from ..enums import Role
from ..datetime_utils import utc_now


def create_user(
    session: Session, 
    email: str, 
    password: str, 
    role: str,
    is_first_admin: bool = False
) -> User:
    """Create a new user with hashed password."""
    user = User(
        email=email, 
        password_hash=hash_password(password), 
        role=role,
        is_first_admin=is_first_admin,
        verified=is_first_admin  # First admin is auto-verified
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> Optional[User]:
    """Authenticate user by email and password."""
    statement = select(User).where(User.email == email).where(User.is_active == True)
    user = session.exec(statement).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """Get user by ID."""
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    """Get active user by email."""
    statement = select(User).where(User.email == email).where(User.is_active == True)
    return session.exec(statement).first()


def update_user_password(session: Session, user_id: int, new_password: str) -> Optional[User]:
    """Update user password hash."""
    user = session.get(User, user_id)
    if not user or not getattr(user, "is_active", True):
        return None
    user.password_hash = hash_password(new_password)
    if not getattr(user, "email_verified", False):
        user.email_verified = True
        user.email_verified_at = utc_now()
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def mark_user_email_verified(session: Session, user_id: int) -> Optional[User]:
    """Mark a user's email as verified."""
    user = session.get(User, user_id)
    if not user or not getattr(user, "is_active", True):
        return None
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = utc_now()
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def get_all_users(session: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Get all users with pagination."""
    statement = (
        select(User)
        .where(User.is_active == True)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return session.exec(statement).all()


def count_users(session: Session) -> int:
    """Count all users."""
    statement = select(func.count()).select_from(User).where(User.is_active == True)
    return session.exec(statement).one()


def verify_admin(session: Session, admin_user_id: int, verified_by_admin_id: int) -> Optional[User]:
    """
    Verify an admin user.
    Only the first admin can verify other admins.
    """
    admin = session.get(User, admin_user_id)
    if not admin:
        return None
    if admin.role != Role.admin:
        return None
    
    admin.verified = True
    admin.verified_at = utc_now()
    admin.verified_by_admin_id = verified_by_admin_id
    
    session.add(admin)
    session.commit()
    session.refresh(admin)
    return admin


def update_user_verification(
    session: Session, 
    user_id: int, 
    verified: bool, 
    verified_by_admin_id: int
) -> Optional[User]:
    """Update user verification status."""
    user = session.get(User, user_id)
    if not user:
        return None
    
    user.verified = verified
    if verified:
        user.verified_at = utc_now()
        user.verified_by_admin_id = verified_by_admin_id
    else:
        user.verified_at = None
        user.verified_by_admin_id = None
    
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def get_pending_admins(session: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Get all unverified admin users."""
    statement = (
        select(User)
        .where(User.role == Role.admin)
        .where(User.is_first_admin == False)
        .where(User.verified == False)
        .where(User.is_active == True)
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(skip)
        .limit(limit)
    )
    return session.exec(statement).all()


def count_pending_admins(session: Session) -> int:
    """Count unverified admin users."""
    statement = (
        select(func.count())
        .select_from(User)
        .where(User.role == Role.admin)
        .where(User.is_first_admin == False)
        .where(User.verified == False)
        .where(User.is_active == True)
    )
    return session.exec(statement).one()


def purge_expired_unverified_users(
    session: Session,
    older_than_days: int = 15,
    email: Optional[str] = None,
) -> int:
    """
    Hard-delete stale email-unverified users older than `older_than_days`.
    Safety rule: delete only if there is no placement history.
    - Student side history: applications/offers
    - Company side history: jobs/offers
    """
    cutoff = utc_now() - timedelta(days=older_than_days)
    statement = (
        select(User)
        .where(User.email_verified == False)
        .where(User.created_at <= cutoff)
    )
    if email:
        statement = statement.where(User.email == email)

    candidates = session.exec(statement).all()
    if not candidates:
        return 0

    deleted = 0
    for user in candidates:
        if user.is_first_admin:
            continue

        student = session.exec(
            select(Student).where(Student.user_id == user.id)
        ).first()
        company = session.exec(
            select(Company).where(Company.user_id == user.id)
        ).first()

        if student:
            has_applications = session.exec(
                select(Application.id).where(Application.student_id == student.id)
            ).first()
            if has_applications:
                continue

            has_student_offers = session.exec(
                select(Offer.id).where(Offer.student_id == student.id)
            ).first()
            if has_student_offers:
                continue

        if company:
            has_jobs = session.exec(
                select(Job.id).where(Job.company_id == company.id)
            ).first()
            if has_jobs:
                continue

            has_company_offers = session.exec(
                select(Offer.id).where(Offer.company_id == company.id)
            ).first()
            if has_company_offers:
                continue

        if student:
            session.delete(student)
        if company:
            session.delete(company)

        session.delete(user)
        deleted += 1

    if deleted:
        session.commit()

    return deleted

