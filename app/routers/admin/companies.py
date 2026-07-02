from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...audit import log_audit
from ...models import User
from ...schemas import CompanyListOut, PaginationParams

router = APIRouter(
    prefix="/companies",
    tags=["admin-companies"],
    dependencies=[Depends(get_verified_admin)],
)


@router.post("/{company_id}/verify")
def verify_company(
    company_id: int,
    session: Session = Depends(get_session),
):
    verified = crud.verify_company(session, company_id)
    if not verified:
        raise HTTPException(status_code=404, detail="Company not found")

    return verified


@router.get("/", response_model=CompanyListOut)
def admin_list_companies(
    pagination: PaginationParams = Depends(),
    verified: bool = Query(None, description="Filter by verification status"),
    include_inactive: bool = Query(False, description="Include deactivated companies"),
    admin_user: User = Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    items = crud.list_companies(
        session,
        skip=pagination.skip,
        limit=pagination.limit,
        verified=verified,
        include_inactive=include_inactive,
    )
    total = crud.count_companies(session, verified=verified, include_inactive=include_inactive)
    
    log_audit("admin.companies.listed", admin_id=admin_user.id, count=len(items), total=total, verified=verified, include_inactive=include_inactive)

    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.delete("/{company_id}")
def admin_delete_company(
    company_id: int,
    session: Session = Depends(get_session),
):
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
    session: Session = Depends(get_session),
):
    res = crud.reactivate_company(session, company_id)
    if not res:
        raise HTTPException(
            status_code=404,
            detail="Company not found or could not be reactivated"
        )
    return {"reactivated": True}

