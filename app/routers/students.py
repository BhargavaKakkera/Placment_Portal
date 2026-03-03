from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from ..database import get_session
from .. import crud
from ..schemas import StudentCreate
from ..auth import get_current_student
from ..models import Application, Offer

router = APIRouter(prefix="/students", tags=["students"])


@router.post("/", response_model=dict)
def create_student(student_in: StudentCreate, current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    existing = crud.get_student_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Student profile already exists")
    student = crud.create_student(session, current_user.id, **student_in.dict())
    return student


@router.get("/me")
def get_my_student(current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    return student


@router.get("/me/applications")
def my_applications(current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    stmt = select(Application).where(Application.student_id == student.id)
    return session.exec(stmt).all()


@router.post("/offers/{offer_id}/accept")
def accept_offer(offer_id: int, current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    offer = crud.accept_offer(session, offer_id, student.id)
    if not offer:
        raise HTTPException(status_code=400, detail="Cannot accept offer")
    return offer


@router.post("/offers/{offer_id}/decline")
def decline_offer(offer_id: int, current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    offer = session.get(Offer, offer_id)
    if not offer or offer.student_id != student.id:
        raise HTTPException(status_code=403, detail="Not allowed to decline this offer")
    offer.status = "declined"
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return offer


@router.delete("/me")
def delete_my_student(current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    res = crud.delete_student(session, student.id)
    if not res:
        raise HTTPException(status_code=400, detail="Could not delete student")
    return {"deleted": True}


@router.delete("/applications/{application_id}")
def withdraw_application(application_id: int, current_user=Depends(get_current_student), session: Session = Depends(get_session)):
    student = crud.get_student_by_user_id(session, current_user.id)
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")
    res = crud.withdraw_application(session, application_id, student.id)
    if not res:
        raise HTTPException(status_code=400, detail="Could not withdraw application or not authorized")
    return {"withdrawn": True}
