from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session
from ..database import get_session
from .. import crud
from ..schemas import CompanyCreate
from ..auth import get_current_company
from ..models import Job, Application

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("/", response_model=dict)
def create_company_endpoint(company_in: CompanyCreate, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    existing = crud.get_company_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Company profile already exists")
    company = crud.create_company(session, current_user.id, company_in.name)
    return company


@router.get("/me")
def get_my_company(current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    return company


@router.delete("/me")
def delete_my_company(current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    res = crud.delete_company(session, company.id)
    if not res:
        raise HTTPException(status_code=400, detail="Could not delete company")
    return {"deleted": True}


@router.get("/jobs/{job_id}/applicants")
def view_applicants(job_id: int, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    job = session.get(Job, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to view applicants for this job")
    applicants = crud.get_applicants_for_job(session, job_id)
    return applicants


@router.post("/applications/{application_id}/shortlist")
def shortlist(application_id: int, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    try:
        app_obj = crud.shortlist_applicant(session, application_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return app_obj


@router.post("/applications/{application_id}/reject")
def reject(application_id: int, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    try:
        app_obj = crud.reject_applicant(session, application_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return app_obj


@router.patch("/applications/{application_id}")
def update_application_status(application_id: int, status: str, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    # Generic status update endpoint for companies; enforce ownership and allowed transitions
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    job = session.get(Job, application.job_id)
    company = crud.get_company_by_user_id(session, current_user.id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to modify this application")
    allowed = {"shortlisted", "rejected"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail="Invalid status transition")
    application.status = status
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


@router.post("/applications/{application_id}/offers")
def make_offer(application_id: int, ctc: float = Query(...), current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    company = crud.get_company_by_user_id(session, current_user.id)
    job = session.get(Job, application.job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not authorized for this job")
    try:
        offer = crud.create_offer(session, job.id, application.student_id, company.id, ctc)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return offer


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    job = session.get(Job, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this job")
    res = crud.delete_job(session, job_id)
    if not res:
        raise HTTPException(status_code=400, detail="Could not delete job")
    return {"deleted": True}
