"""
Admin router for job management.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...schemas import JobListOut, PaginationParams

router = APIRouter(
    prefix="/jobs",
    tags=["admin-jobs"],
    dependencies=[Depends(get_verified_admin)],
)


@router.get("/", response_model=JobListOut)
def admin_list_jobs(
    pagination: PaginationParams = Depends(),
    session: Session = Depends(get_session),
):
    """List all jobs with pagination (requires verified admin)."""
    items = crud.list_jobs(session, skip=pagination.skip, limit=pagination.limit)
    total = crud.count_jobs(session)

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
    """Close a job posting (requires verified admin)."""
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
    """Delete a job (requires verified admin)."""
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

