import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin, hash_password, create_password_reset_token
from ...audit import log_audit
from ...config import DEBUG
from ...schemas import (
    StudentAdminUpdate,
    AdminStudentProvisionIn,
    AdminStudentProvisionOut,
    PaginationParams,
    StudentListOut,
)
from ...models import User, Student
from ...enums import Branch
from ...enums import Role
from ...logger import get_logger
from ...email_service import send_student_invite_email

router = APIRouter(
    prefix="/students",
    tags=["admin-students"],
    dependencies=[Depends(get_verified_admin)],
)
DEBUG_MODE = DEBUG
logger = get_logger(__name__)


def _send_student_invite_email(email: str, token: str) -> None:
    send_student_invite_email(email, token)


@router.post("/provision", response_model=AdminStudentProvisionOut)
def provision_student(
    payload: AdminStudentProvisionIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    crud.purge_expired_unverified_users(session, older_than_days=15, email=payload.email)

    existing_user = session.exec(select(User).where(User.email == payload.email)).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email already registered")

    existing_student = session.exec(
        select(Student).where(Student.reg_no == payload.reg_no)
    ).first()
    if existing_student:
        raise HTTPException(status_code=409, detail="reg_no already exists")

    temp_password = secrets.token_urlsafe(24)

    try:
        user = User(
            email=payload.email,
            password_hash=hash_password(temp_password),
            role=Role.student,
            email_verified=False,
            is_first_admin=False,
            verified=False,
            is_active=True,
        )
        session.add(user)
        session.flush()

        student = Student(
            user_id=user.id,
            name=payload.name,
            reg_no=payload.reg_no,
            roll_no=payload.roll_no,
            cgpa=payload.cgpa,
            branch=payload.branch,
            gender=payload.gender,
            graduation_year=payload.graduation_year,
            backlogs=payload.backlogs,
        )
        session.add(student)
        session.commit()
        session.refresh(student)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Student/user already exists")

    invite_token = create_password_reset_token(user.id)
    background_tasks.add_task(_send_student_invite_email, user.email, invite_token)

    response = {
        "user_id": user.id,
        "student_id": student.id,
        "invite_sent": True,
        "message": "Invite has been queued for email delivery.",
    }
    if DEBUG_MODE:
        response["invite_token"] = invite_token

    return response


@router.get("/", response_model=StudentListOut)
def admin_list_students(
    pagination: PaginationParams = Depends(),
    branch: Optional[Branch] = Query(None, description="Filter by branch"),
    reg_no: Optional[str] = Query(None, description="Filter by registration number (partial match)"),
    include_inactive: bool = Query(False, description="Include deactivated students"),
    admin_user: User = Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    items = crud.list_students(
        session,
        skip=pagination.skip,
        limit=pagination.limit,
        branch=branch,
        reg_no=reg_no,
        include_inactive=include_inactive,
    )
    total = crud.count_students(
        session,
        branch=branch,
        reg_no=reg_no,
        include_inactive=include_inactive,
    )
    
    log_audit(
        "admin.students.listed",
        admin_id=admin_user.id,
        count=len(items),
        total=total,
        branch=str(branch) if branch else None,
        reg_no=reg_no,
        include_inactive=include_inactive,
    )

    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.patch("/{student_id}")
def admin_update_student(
    student_id: int,
    student_in: StudentAdminUpdate,
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
        **data
    )

    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Student not found or update failed"
        )

    return updated


@router.delete("/{student_id}")
def admin_delete_student(
    student_id: int,
    session: Session = Depends(get_session),
):
    try:
        res = crud.delete_student(session, student_id)
    except ValueError as e:
        error_msg = str(e)
        status_code = 404 if "not found" in error_msg.lower() else 409
        raise HTTPException(
            status_code=status_code,
            detail=error_msg
        )
    
    if not res:
        raise HTTPException(status_code=409, detail="Could not delete student")

    return {"deleted": True}


@router.post("/{student_id}/reactivate")
def admin_reactivate_student(
    student_id: int,
    session: Session = Depends(get_session),
):
    res = crud.reactivate_student(session, student_id)
    if not res:
        raise HTTPException(
            status_code=404,
            detail="Student not found or could not be reactivated"
        )
    return {"reactivated": True}
