from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..database import get_session
from .. import crud
from ..schemas import StudentCreate, StudentUpdate, StudentOut
from ..auth import get_current_student
from ..models import Application, Offer
from ..enums import OfferStatus

router = APIRouter(prefix="/students", tags=["students"])


# ---------------------------
# CREATE STUDENT PROFILE
# ---------------------------

@router.post("/", response_model=StudentOut)
def create_student(
    student_in: StudentCreate,
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    existing = crud.get_student_by_user_id(session, current_user.id)

    if existing:
        raise HTTPException(
            status_code=400,
            detail="Student profile already exists"
        )

    student = crud.create_student(
        session,
        current_user.id,
        **student_in.model_dump(mode="json")
    )

    return student


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
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    data = student_in.model_dump(exclude_unset=True, mode="json")

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

    return updated


# ---------------------------
# VIEW MY APPLICATIONS
# ---------------------------

@router.get("/me/applications")
def my_applications(
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    stmt = select(Application).where(Application.student_id == student.id)

    return session.exec(stmt).all()


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

    if offer.status != OfferStatus.offered:
        raise HTTPException(
            status_code=400,
            detail="Only pending offered status can be declined"
        )

    offer.status = OfferStatus.declined

    session.add(offer)
    session.commit()
    session.refresh(offer)

    return offer


# ---------------------------
# DELETE MY PROFILE
# ---------------------------

@router.delete("/me")
def delete_my_student(
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    res = crud.delete_student(session, student.id)

    if not res:
        raise HTTPException(
            status_code=400,
            detail="Could not delete student"
        )

    return {"deleted": True}


# ---------------------------
# WITHDRAW APPLICATION
# ---------------------------

@router.delete("/applications/{application_id}")
def withdraw_application(
    application_id: int,
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    res = crud.withdraw_application(
        session,
        application_id,
        student.id
    )

    if not res:
        raise HTTPException(
            status_code=400,
            detail="Could not withdraw application or not authorized"
        )

    return {"withdrawn": True}



@router.get("/me/offers")
def my_offers(
    current_user=Depends(get_current_student),
    session: Session = Depends(get_session),
):
    student = crud.get_student_by_user_id(session, current_user.id)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    stmt = select(Offer).where(Offer.student_id == student.id)

    return session.exec(stmt).all()
