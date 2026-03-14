from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from sqlalchemy.exc import IntegrityError
from ..database import get_session
from .. import crud
from ..schemas import (
    CompanyCreate,
    CompanyOut,
    CompanyApplicationStatusUpdate,
    CompanyAcceptedOfferListOut,
    CompanyApplicantListOut,
    JobListOut,
    PaginationParams,
)
from ..auth import get_current_company
from ..models import Job, Application
from ..enums import CompanyApplicationAction

router = APIRouter(prefix="/companies", tags=["companies"])


@router.post("/", response_model=CompanyOut)
def create_company_endpoint(company_in: CompanyCreate, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    existing = crud.get_company_by_user_id(session, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Company profile already exists")
    try:
        company = crud.create_company(session, current_user.id, company_in.name)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Company profile already exists or account is inactive")
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
    try:
        res = crud.delete_company(session, company.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not res:
        raise HTTPException(status_code=400, detail="Could not delete company")
    return {"deleted": True}


@router.get("/jobs/{job_id}/applicants", response_model=CompanyApplicantListOut)
def view_applicants(
    job_id: int,
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_current_company),
    session: Session = Depends(get_session),
):
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    job = session.get(Job, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to view applicants for this job")
    items = crud.list_company_applicant_summaries(
        session,
        job_id,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_applicants_for_job(session, job_id)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.patch("/applications/{application_id}")
def update_application_status(
    application_id: int,
    payload: CompanyApplicationStatusUpdate,
    current_user=Depends(get_current_company),
    session: Session = Depends(get_session),
):
    # Unified application action endpoint for companies.
    application = session.get(Application, application_id)
    if not application:
        raise HTTPException(
            status_code=404,
            detail="Application not found (it may have been withdrawn)"
        )
    job = session.get(Job, application.job_id)
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to modify this application")
    if payload.status not in {
        CompanyApplicationAction.shortlisted,
        CompanyApplicationAction.rejected,
        CompanyApplicationAction.offered,
    }:
        raise HTTPException(
            status_code=422,
            detail="Invalid status. Allowed: shortlisted, rejected, offered"
        )
    try:
        return crud.apply_company_action(
            session=session,
            application=application,
            job=job,
            company_id=company.id,
            action=payload.status,
            ctc=payload.ctc,
            offer_response_deadline=payload.offer_response_deadline,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, current_user=Depends(get_current_company), session: Session = Depends(get_session)):
    company = crud.get_company_by_user_id(session, current_user.id)
    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")
    job = session.get(Job, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete this job")
    try:
        res = crud.delete_job(session, job_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not res:
        raise HTTPException(status_code=400, detail="Could not delete job")
    return {"deleted": True}


@router.get("/me/jobs", response_model=JobListOut)
def my_jobs(
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_current_company),
    session: Session = Depends(get_session),
):
    company = crud.get_company_by_user_id(session, current_user.id)

    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")

    items = crud.list_company_jobs(
        session,
        company.id,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_company_jobs(session, company.id)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.get("/me/offers/accepted", response_model=CompanyAcceptedOfferListOut)
def my_accepted_offers(
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_current_company),
    session: Session = Depends(get_session),
):
    company = crud.get_company_by_user_id(session, current_user.id)

    if not company:
        raise HTTPException(status_code=404, detail="Company profile not found")

    items = crud.list_company_accepted_offer_summaries(
        session,
        company.id,
        skip=pagination.skip,
        limit=pagination.limit,
    )
    total = crud.count_company_accepted_offers(session, company.id)
    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }
