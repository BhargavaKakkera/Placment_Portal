"""
Admin router for offer management.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...schemas import PaginationParams

router = APIRouter(
    prefix="/offers",
    tags=["admin-offers"],
    dependencies=[Depends(get_verified_admin)],
)


@router.get("/")
def admin_list_offers(
    pagination: PaginationParams = Depends(),
    session: Session = Depends(get_session),
):
    items = crud.list_offers_admin_summaries(session, skip=pagination.skip, limit=pagination.limit)
    total = crud.count_offers_all(session)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.delete("/{offer_id}")
def admin_delete_offer(
    offer_id: int,
    session: Session = Depends(get_session),
):
    ok = crud.admin_delete_offer(session, offer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Offer not found or could not be deleted")
    return {"deleted": True}
