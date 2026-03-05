"""
User CRUD operations for authentication and admin management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import User
from ..auth import hash_password, verify_password
from ..enums import Role


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
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user_by_id(session: Session, user_id: int) -> Optional[User]:
    """Get user by ID."""
    return session.get(User, user_id)


def get_all_users(session: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Get all users with pagination."""
    statement = select(User).offset(skip).limit(limit)
    return session.exec(statement).all()


def count_users(session: Session) -> int:
    """Count all users."""
    statement = select(func.count()).select_from(User)
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
    admin.verified_at = datetime.utcnow()
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
        user.verified_at = datetime.utcnow()
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
    )
    return session.exec(statement).one()

