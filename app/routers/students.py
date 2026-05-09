from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..database import get_session
from .. import crud
from ..schemas import (
    StudentUpdate,
    StudentOut,
    StudentApplicationListOut,
    StudentOfferItemOut,
    StudentOfferListOut,
    PaginationParams,
)
from ..auth import get_current_student
from ..models import Offer
from ..enums import OfferStatus
from ..logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/students", tags=["students"])


def _student_update_data(student_in: StudentUpdate) -> dict:
    """Build an update dict without nulling non-nullable academic fields."""
    data = student_in.model_dump(exclude_unset=True, mode="json")
    for field in ("cgpa", "backlogs"):
        if data.get(field) is None:
            data.pop(field, None)
    return data


# ---------------------------
# GET MY PROFILE
# ---------------------------

@router.get("/me", response_model=StudentOut)
def get_my_student(
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    return student


# ---------------------------
# UPDATE PROFILE (student editable fields)
# ---------------------------

@router.patch("/me", response_model=StudentOut)
def update_my_profile(
    student_in: StudentUpdate,
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    try:
        student = crud.get_student_by_user_id(session, current_user.id)

        if not student:
            raise HTTPException(
                status_code=404,
                detail="Student profile not found"
            )

        # Convert model to dict, excluding unset fields
        data = _student_update_data(student_in)
        
        logger.debug(f"Update data for student {student.id}: {data}")

        if not data:
            raise HTTPException(
                status_code=400,
                detail="No update fields provided"
            )

        updated = crud.update_student(
            session,
            student.id,
            **data
        )
        
        if not updated:
            raise HTTPException(
                status_code=500,
                detail="Failed to update student profile"
            )

        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating student profile: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


# ---------------------------
# VIEW MY APPLICATIONS
# ---------------------------

@router.get("/me/applications", response_model=StudentApplicationListOut)
def my_applications(
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    items = crud.list_student_application_summaries(
        session,
        student.id,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_student_applications(session, student.id)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


# ---------------------------
# ACCEPT OFFER
# ---------------------------

@router.post("/offers/{offer_id}/accept")
def accept_offer(
    offer_id: int,
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    offer = crud.accept_offer(session, offer_id, student.id)

    if not offer:
        raise HTTPException(
            status_code=400,
            detail="Cannot accept offer"
        )

    return offer


# ---------------------------
# DECLINE OFFER
# ---------------------------

@router.post("/offers/{offer_id}/decline")
def decline_offer(
    offer_id: int,
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    offer = session.get(Offer, offer_id)
    if not offer or offer.student_id != student.id:
        raise HTTPException(
            status_code=403,
            detail="Not allowed to decline this offer"
        )

    if student.locked_offer_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Cannot decline after accepting an offer"
        )

    declined = crud.decline_offer(session, offer_id, student.id)
    if not declined:
        raise HTTPException(
            status_code=400,
            detail="Only pending offered status can be declined"
        )

    return declined


# ---------------------------
# WITHDRAW APPLICATION
# ---------------------------

@router.get("/me/offers", response_model=StudentOfferListOut)
def my_offers(
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    items = crud.list_student_offer_summaries(
        session,
        student.id,
        status=OfferStatus.offered,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_student_offers(session, student.id, status=OfferStatus.offered)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.get("/me/offers/accepted", response_model=StudentOfferListOut)
def my_accepted_offers(
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    items = crud.list_student_offer_summaries(
        session,
        student.id,
        status=OfferStatus.accepted,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_student_offers(session, student.id, status=OfferStatus.accepted)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }
