"""
Student CRUD operations for student profile management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Student, User


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
    admin_user_id: int = None,
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

    if "verified" in data and data.get("verified"):
        student.verified_at = datetime.utcnow()
        if admin_user_id is not None:
            student.verified_by_admin_id = admin_user_id
    elif "verified" in data and data.get("verified") is False:
        student.verified_at = None
        student.verified_by_admin_id = None

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
    verified: bool = None
) -> List[Student]:
    """List active students with optional verification filtering."""
    statement = select(Student).where(Student.is_active == True)
    if verified is not None:
        statement = statement.where(Student.verified == verified)
    statement = statement.offset(skip).limit(limit)
    return session.exec(statement).all()


def count_students(session: Session, verified: bool = None) -> int:
    """Count active students with optional verification filtering."""
    statement = select(func.count()).select_from(Student).where(Student.is_active == True)
    if verified is not None:
        statement = statement.where(Student.verified == verified)
    return session.exec(statement).one()


def verify_student(
    session: Session,
    student_id: int,
    admin_user_id: int
) -> Optional[Student]:
    """Verify a student profile."""
    student = session.get(Student, student_id)
    if not student or not getattr(student, "is_active", True):
        return None
    student.verified = True
    student.verified_at = datetime.utcnow()
    student.verified_by_admin_id = admin_user_id
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def count_placed_students(session: Session) -> int:
    """Count active students who have accepted an offer (placed students)."""
    statement = (
        select(func.count())
        .select_from(Student)
        .where(Student.is_active == True)
        .where(Student.locked_offer_id != None)
    )
    return session.exec(statement).one()
