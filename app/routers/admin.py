from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..database import get_session
from .. import crud
from ..auth import get_current_admin
from ..schemas import StudentAdminUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------
# COMPANY MANAGEMENT
# ---------------------------

@router.post("/companies/{company_id}/verify")
def verify_company(
    company_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    try:
        verified = crud.verify_company(session, company_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Unable to verify company")

    if not verified:
        raise HTTPException(status_code=404, detail="Company not found")

    return verified


@router.get("/companies")
def admin_list_companies(
    skip: int = Query(0, ge=0, description="Pagination skip (offset)"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit (max 100)"),
    verified: bool = Query(None, description="Filter by verification status"),
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    items = crud.list_companies(session, skip=skip, limit=limit, verified=verified)
    total = crud.count_companies(session, verified=verified)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.delete("/companies/{company_id}")
def admin_delete_company(
    company_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    res = crud.delete_company(session, company_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Company not found or could not be deleted"
        )

    return {"deleted": True}


# ---------------------------
# STUDENT MANAGEMENT
# ---------------------------

@router.post("/students/{student_id}/verify")
def verify_student(
    student_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    verified = crud.verify_student(session, student_id, current_user.id)

    if not verified:
        raise HTTPException(status_code=404, detail="Student not found")

    return verified


@router.get("/students")
def admin_list_students(
    skip: int = Query(0, ge=0, description="Pagination skip (offset)"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit (max 100)"),
    verified: bool = Query(None, description="Filter by verification status"),
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    items = crud.list_students(session, skip=skip, limit=limit, verified=verified)
    total = crud.count_students(session, verified=verified)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.patch("/students/{student_id}")
def admin_update_student(
    student_id: int,
    student_in: StudentAdminUpdate,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    data = student_in.model_dump(exclude_unset=True, mode="json")

    if not data:
        raise HTTPException(
            status_code=400,
            detail="No update fields provided"
        )

    updated = crud.update_student(
        session,
        student_id,
        admin_user_id=current_user.id,
        **data
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Student not found or update failed"
        )

    return updated


@router.delete("/students/{student_id}")
def admin_delete_student(
    student_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    res = crud.delete_student(session, student_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Student not found or could not be deleted"
        )

    return {"deleted": True}


# ---------------------------
# JOB MANAGEMENT
# ---------------------------

@router.get("/jobs")
def admin_list_jobs(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    items = crud.list_jobs(session, skip=skip, limit=limit)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": len(items)
    }


@router.post("/jobs/{job_id}/close")
def close_job(
    job_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    try:
        job = crud.close_job(session, job_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return job


@router.delete("/jobs/{job_id}")
def admin_delete_job(
    job_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    res = crud.delete_job(session, job_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Job not found or could not be deleted"
        )

    return {"deleted": True}


# ---------------------------
# APPLICATION MANAGEMENT
# ---------------------------

@router.get("/applications")
def admin_list_applications(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    items = crud.list_applications(session, skip=skip, limit=limit)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": len(items)
    }


@router.delete("/applications/{application_id}")
def admin_delete_application(
    application_id: int,
    current_user=Depends(get_current_admin),
    session: Session = Depends(get_session),
):
    res = crud.delete_application(session, application_id)

    if not res:
        raise HTTPException(
            status_code=404,
            detail="Application not found or could not be deleted"
        )

    return {"deleted": True}
