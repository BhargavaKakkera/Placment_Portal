"""
Student CRUD operations for student profile management.
"""

from datetime import datetime
from sqlmodel import Session, select, func
from typing import Optional, List
from ..models import Student


def create_student(session: Session, user_id: int, **data) -> Student:
    """Create a new student profile."""
    student = Student(user_id=user_id, **data)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def get_student_by_user_id(session: Session, user_id: int) -> Optional[Student]:
    """Get student profile by user ID."""
    statement = select(Student).where(Student.user_id == user_id)
    return session.exec(statement).first()


def get_student_by_id(session: Session, student_id: int) -> Optional[Student]:
    """Get student profile by student ID."""
    return session.get(Student, student_id)


def update_student(
    session: Session, 
    student_id: int, 
    admin_user_id: int = None, 
    **data
) -> Optional[Student]:
    """Update student profile."""
    student = session.get(Student, student_id)
    if not student:
        return None
    
    # Apply provided fields
    for key, value in data.items():
        if not hasattr(student, key):
            continue
        setattr(student, key, value)

    # If verified explicitly set by admin, update audit fields
    if 'verified' in data and data.get('verified'):
        student.verified_at = datetime.utcnow()
        if admin_user_id is not None:
            student.verified_by_admin_id = admin_user_id
    elif 'verified' in data and data.get('verified') is False:
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
    """Delete student profile."""
    student = session.get(Student, student_id)
    if not student:
        return None
    try:
        session.delete(student)
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
    """List students with optional filtering."""
    statement = select(Student)
    if verified is not None:
        statement = statement.where(Student.verified == verified)
    statement = statement.offset(skip).limit(limit)
    return session.exec(statement).all()


def count_students(session: Session, verified: bool = None) -> int:
    """Count students with optional filtering."""
    statement = select(func.count()).select_from(Student)
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
    if not student:
        return None
    student.verified = True
    student.verified_at = datetime.utcnow()
    student.verified_by_admin_id = admin_user_id
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def count_placed_students(session: Session) -> int:
    """Count students who have accepted an offer (placed students)."""
    statement = select(func.count()).select_from(Student).where(Student.locked_offer_id != None)
    return session.exec(statement).one()

