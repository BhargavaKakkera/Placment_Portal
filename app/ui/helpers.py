from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
import secrets

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlmodel import Session, select

from .. import crud
from ..crud.offer_crud import get_application_block_reason, get_student_acceptance_state
from ..datetime_utils import to_utc_naive, utc_now
from ..enums import Branch, CompanyApplicationAction, Role, RoleType
from ..models import Application, Company, Job, Student, User

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def _fmt_dt(value: Optional[datetime]) -> str:
    return "-" if value is None else value.strftime("%Y-%m-%d %H:%M")


templates.env.filters["fmt_datetime"] = _fmt_dt


def set_flash(request: Request, message: str, category: str = "info") -> None:
    request.session["_flash"] = {"message": message, "category": category}


def render(request: Request, template: str, **context):
    csrf_token = request.session.get("_csrf_token")
    if not csrf_token:
        csrf_token = secrets.token_urlsafe(32)
        request.session["_csrf_token"] = csrf_token

    base = {
        "request": request,
        "flash": request.session.pop("_flash", None),
        "csrf_token": csrf_token,
        "Role": Role,
        "Branch": Branch,
        "RoleType": RoleType,
        "CompanyApplicationAction": CompanyApplicationAction,
    }
    base.update(context)
    return templates.TemplateResponse(template, base)


def redirect_to(request: Request, route_name: str, message: Optional[str] = None, category: str = "info"):
    if message:
        set_flash(request, message, category)
    return RedirectResponse(request.url_for(route_name), status_code=303)


def redirect_path(request: Request, path: str, message: Optional[str] = None, category: str = "info"):
    if message:
        set_flash(request, message, category)
    return RedirectResponse(path, status_code=303)


def txt(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def flt(value) -> Optional[float]:
    value = txt(value)
    return float(value) if value is not None else None


def int_or_none(value) -> Optional[int]:
    value = txt(value)
    return int(value) if value is not None else None


def dt(value) -> Optional[datetime]:
    value = txt(value)
    return to_utc_naive(datetime.fromisoformat(value)) if value else None


def branches(values: list[str]) -> Optional[list[Branch]]:
    return [Branch(v) for v in values if v] or None


def validation_message(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        if errors:
            return "; ".join(str(item.get("msg", "Invalid input")) for item in errors)
        return "Invalid input"
    return str(exc) or "Invalid input"


async def read_form_with_csrf(request: Request):
    """
    Read POST form data and validate CSRF token against session token.

    Raises:
        ValueError: If CSRF token is missing or invalid
    """
    form = await request.form()
    form_token = str(form.get("csrf_token", "")).strip()
    session_token = str(request.session.get("_csrf_token", "")).strip()
    if not form_token or not session_token or not secrets.compare_digest(form_token, session_token):
        raise ValueError("Invalid or missing CSRF token. Please refresh and try again.")
    return form


def current_user(request: Request, session: Session) -> Optional[User]:
    user_id = request.session.get("ui_user_id")
    if not user_id:
        return None
    user = session.get(User, user_id)
    if not user or not getattr(user, "is_active", True):
        request.session.clear()
        return None
    return user


def home_for(user: Optional[User]) -> str:
    if not user:
        return "/ui/"
    if user.role == Role.student:
        return "/ui/student"
    if user.role == Role.company:
        return "/ui/company"
    return "/ui/admin"


def require_user(request: Request, session: Session, role: Optional[Role] = None, verified_admin: bool = False):
    user = current_user(request, session)
    if not user:
        return None, redirect_to(request, "ui_login", "Please log in first.", "warning")
    if role and user.role != role:
        return None, redirect_to(request, "ui_home", "You do not have access to that page.", "danger")
    if user.role in {Role.company, Role.admin} and not getattr(user, "email_verified", False):
        return None, redirect_to(request, "ui_verify_email", "Please verify email first.", "warning")
    if verified_admin and user.role == Role.admin and not user.is_first_admin and not user.verified:
        return None, redirect_to(request, "ui_home", "Admin approval is still pending.", "warning")
    return user, None


def require_student_profile(request: Request, session: Session, user: User):
    student = crud.get_student_by_user_id(session, user.id)
    if not student:
        return None, redirect_to(request, "ui_home", "Student profile not found.", "warning")
    return student, None


def require_company_profile(request: Request, session: Session, user: User):
    company = crud.get_company_by_user_id(session, user.id)
    if not company:
        return None, redirect_to(request, "ui_company_profile", "Create your company profile first.", "warning")
    return company, None


def is_public_job_visible(session: Session, job: Optional[Job]) -> bool:
    if not job or job.closed:
        return False
    if job.application_deadline and to_utc_naive(job.application_deadline) < utc_now():
        return False
    company = session.get(Company, job.company_id)
    return bool(company and getattr(company, "is_active", True) and getattr(company, "verified", False))


def eligible_jobs(session: Session, student: Student) -> list[Job]:
    jobs = crud.list_verified_jobs(session, skip=0, limit=None)
    applied_job_ids = set(
        session.exec(
            select(Application.job_id).where(Application.student_id == student.id)
        ).all()
    )
    
    # Cache acceptance state to avoid N+1 query (fetch once instead of per job)
    acceptance_state = get_student_acceptance_state(session, student.id)
    
    eligible = []
    for job in jobs:
        if job.id in applied_job_ids:
            continue
        if job.min_cgpa is not None and student.cgpa < job.min_cgpa:
            continue
        if job.max_backlogs is not None and student.backlogs > job.max_backlogs:
            continue
        if job.allowed_branches:
            allowed = [b.strip() for b in job.allowed_branches.split(",") if b.strip()]
            branch = student.branch.value if hasattr(student.branch, "value") else str(student.branch)
            if branch not in allowed:
                continue
        if job.application_deadline and to_utc_naive(job.application_deadline) < utc_now():
            continue
        
        # Check application block reason using cached state
        role_type = job.role_type if hasattr(job, "role_type") else RoleType.full_time
        if acceptance_state["has_accepted_full_time"] and role_type == RoleType.full_time:
            continue
        if acceptance_state["has_accepted_internship"] and role_type == RoleType.internship:
            continue
        
        eligible.append(job)
    return eligible
