"""
Student CRUD operations for student profile management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Student, User, Offer
from ..enums import Branch
from ..enums import OfferStatus


def create_student(session: Session, user_id: int, **data) -> Student:
    """Create a new student profile."""
    student = Student(user_id=user_id, **data)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def get_student_by_user_id(session: Session, user_id: int) -> Optional[Student]:
    """Get active student profile by user ID."""
    statement = select(Student).where(Student.user_id == user_id).where(Student.is_active == True)
    return session.exec(statement).first()


def get_student_by_id(session: Session, student_id: int) -> Optional[Student]:
    """Get active student profile by student ID."""
    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        return None
    return student


def update_student(
    session: Session,
    student_id: int,
    **data
) -> Optional[Student]:
    """Update student profile."""
    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        return None

    for key, value in data.items():
        if not hasattr(student, key):
            continue
        setattr(student, key, value)

    session.add(student)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return None
    session.refresh(student)
    return student


def delete_student(session: Session, student_id: int) -> Optional[bool]:
    """Soft-delete student profile and linked user account."""
    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        return None

    try:
        student.is_active = False
        student.deactivated_at = datetime.utcnow()
        session.add(student)

        user = session.get(User, student.user_id)
        if user and getattr(user, "is_active", True):
            user.is_active = False
            user.deactivated_at = datetime.utcnow()
            session.add(user)

        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def reactivate_student(session: Session, student_id: int) -> Optional[bool]:
    """Reactivate student profile and linked user account."""
    student = session.get(Student, student_id)
    if not student:
        return None
    if getattr(student, "is_active", True):
        return True

    try:
        student.is_active = True
        student.deactivated_at = None
        session.add(student)

        user = session.get(User, student.user_id)
        if user and not getattr(user, "is_active", True):
            user.is_active = True
            user.deactivated_at = None
            session.add(user)

        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def list_students(
    session: Session,
    skip: int = 0,
    limit: int = 100,
    branch: Optional[Branch] = None,
    include_inactive: bool = False,
) -> List[Student]:
    """List students with optional branch filtering."""
    statement = select(Student)
    if not include_inactive:
        statement = statement.where(Student.is_active == True)
    if branch is not None:
        statement = statement.where(Student.branch == branch)
    statement = statement.order_by(Student.reg_no.asc(), Student.id.asc()).offset(skip).limit(limit)
    return session.exec(statement).all()


def count_students(
    session: Session,
    branch: Optional[Branch] = None,
    include_inactive: bool = False,
) -> int:
    """Count students with optional branch filtering."""
    statement = select(func.count()).select_from(Student)
    if not include_inactive:
        statement = statement.where(Student.is_active == True)
    if branch is not None:
        statement = statement.where(Student.branch == branch)
    return session.exec(statement).one()


def count_placed_students(session: Session) -> int:
    """Count active students who have accepted an offer (placed students)."""
    statement = (
        select(func.count(func.distinct(Student.id)))
        .select_from(Student)
        .join(Offer, Offer.student_id == Student.id)
        .where(Student.is_active == True)
        .where(Offer.status == OfferStatus.accepted)
    )
    return session.exec(statement).one()
