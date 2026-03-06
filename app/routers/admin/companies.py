"""
Admin router for company management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin

router = APIRouter(prefix="/companies", tags=["admin-companies"])


@router.post("/{company_id}/verify")
def verify_company(
    company_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Verify a company (requires verified admin)."""
    try:
        verified = crud.verify_company(session, company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to verify company")

    if not verified:
        raise HTTPException(status_code=404, detail="Company not found")

    return verified


@router.get("/")
def admin_list_companies(
    skip: int = Query(0, ge=0, description="Pagination skip (offset)"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit (max 100)"),
    verified: bool = Query(None, description="Filter by verification status"),
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """List all companies with pagination (requires verified admin)."""
    items = crud.list_companies(session, skip=skip, limit=limit, verified=verified)
    total = crud.count_companies(session, verified=verified)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.delete("/{company_id}")
def admin_delete_company(
    company_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Delete a company (requires verified admin)."""
    try:
        res = crud.delete_company(session, company_id)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Company not found or could not be deleted"
        )

    return {"deleted": True}


@router.post("/{company_id}/reactivate")
def admin_reactivate_company(
    company_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Reactivate a company and linked user account (requires verified admin)."""
    res = crud.reactivate_company(session, company_id)
    if not res:
        raise HTTPException(
            status_code=404,
            detail="Company not found or could not be reactivated"
        )
    return {"reactivated": True}

