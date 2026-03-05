"""
Admin router for application management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin

router = APIRouter(prefix="/applications", tags=["admin-applications"])


@router.get("/")
def admin_list_applications(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """List all applications with pagination (requires verified admin)."""
    items = crud.list_applications(session, skip=skip, limit=limit)
    total = crud.count_applications(session)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.delete("/{application_id}")
def admin_delete_application(
    application_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Delete an application (requires verified admin)."""
    res = crud.delete_application(session, application_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Application not found or could not be deleted"
        )

    return {"deleted": True}

