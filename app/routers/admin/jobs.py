"""
Admin router for job management.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin

router = APIRouter(prefix="/jobs", tags=["admin-jobs"])


@router.get("/")
def admin_list_jobs(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """List all jobs with pagination (requires verified admin)."""
    items = crud.list_jobs(session, skip=skip, limit=limit)
    total = crud.count_jobs(session)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.post("/{job_id}/close")
def close_job(
    job_id: int,
    current_user=Depends(get_verified_admin),
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
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Delete a job (requires verified admin)."""
    res = crud.delete_job(session, job_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Job not found or could not be deleted"
        )

    return {"deleted": True}

