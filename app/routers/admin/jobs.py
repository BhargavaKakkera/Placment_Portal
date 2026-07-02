from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...audit import log_audit
from ...models import User
from ...schemas import JobListOut, PaginationParams, JobOut

router = APIRouter(
    prefix="/jobs",
    tags=["admin-jobs"],
    dependencies=[Depends(get_verified_admin)],
)

def _serialize_job_with_company_name(session: Session, job) -> dict:
    data = JobOut.model_validate(job).model_dump()
    company = crud.get_company_by_id(session, job.company_id)
    data["company_name"] = company.name if company else None
    return data


@router.get("/", response_model=JobListOut)
def admin_list_jobs(
    pagination: PaginationParams = Depends(),
    company_id: Optional[int] = Query(None, description="Filter by company ID"),
    company_name: Optional[str] = Query(None, description="Filter by company name (partial match)"),
    admin_user: User = Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    rows = crud.list_jobs(
        session,
        skip=pagination.skip,
        limit=pagination.limit,
        company_id=company_id,
        company_name=company_name,
    )
    items = [_serialize_job_with_company_name(session, job) for job in rows]
    total = crud.count_jobs(session, company_id=company_id, company_name=company_name)
    
    log_audit(
        "admin.jobs.listed",
        admin_id=admin_user.id,
        count=len(items),
        total=total,
        company_id=company_id,
        company_name=company_name,
    )

    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.post("/{job_id}/close")
def close_job(
    job_id: int,
    session: Session = Depends(get_session),
):
    try:
        job = crud.close_job(session, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return job


@router.delete("/{job_id}")
def admin_delete_job(
    job_id: int,
    session: Session = Depends(get_session),
):
    try:
        res = crud.delete_job(session, job_id)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Job not found or could not be deleted"
        )

    return {"deleted": True}
