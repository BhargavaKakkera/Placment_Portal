"""
Admin router for student management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...schemas import StudentAdminUpdate

router = APIRouter(prefix="/students", tags=["admin-students"])


@router.post("/{student_id}/verify")
def verify_student(
    student_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Verify a student (requires verified admin)."""
    verified = crud.verify_student(session, student_id, current_user.id)

    if not verified:
        raise HTTPException(status_code=404, detail="Student not found")

    return verified


@router.get("/")
def admin_list_students(
    skip: int = Query(0, ge=0, description="Pagination skip (offset)"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit (max 100)"),
    verified: bool = Query(None, description="Filter by verification status"),
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """List all students with pagination (requires verified admin)."""
    items = crud.list_students(session, skip=skip, limit=limit, verified=verified)
    total = crud.count_students(session, verified=verified)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.patch("/{student_id}")
def admin_update_student(
    student_id: int,
    student_in: StudentAdminUpdate,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Update a student profile (requires verified admin)."""
    data = student_in.model_dump(exclude_unset=True, mode="json")

    if not data:
        raise HTTPException(
            status_code=400,
            detail="No update fields provided"
        )

    updated = crud.update_student(
        session,
        student_id,
        admin_user_id=current_user.id,
        **data
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Student not found or update failed"
        )

    return updated


@router.delete("/{student_id}")
def admin_delete_student(
    student_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Delete a student (requires verified admin)."""
    res = crud.delete_student(session, student_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Student not found or could not be deleted"
        )

    return {"deleted": True}

