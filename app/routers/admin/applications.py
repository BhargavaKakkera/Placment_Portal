"""
Admin router for application management.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...schemas import ApplicationListOut, PaginationParams

router = APIRouter(
    prefix="/applications",
    tags=["admin-applications"],
    dependencies=[Depends(get_verified_admin)],
)


@router.get("/", response_model=ApplicationListOut)
def admin_list_applications(
    pagination: PaginationParams = Depends(),
    session: Session = Depends(get_session),
):
    """List all applications with pagination (requires verified admin)."""
    items = crud.list_applications(
        session,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_applications(session)

    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.delete("/{application_id}")
def admin_delete_application(
    application_id: int,
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

