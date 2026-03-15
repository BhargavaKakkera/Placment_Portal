from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from . import crud
from .auth import create_access_token, create_email_verification_token, create_password_reset_token, hash_password
from .database import engine
from .datetime_utils import to_utc_naive, utc_now
from .enums import Branch, CompanyApplicationAction, OfferStatus, Role, RoleType
from .models import Application, Company, Job, Student, User
from .crud.offer_crud import get_application_block_reason

router = APIRouter(prefix="/ui", tags=["ui"])
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


def _fmt_dt(value: Optional[datetime]) -> str:
    return "-" if value is None else value.strftime("%Y-%m-%d %H:%M")


templates.env.filters["fmt_datetime"] = _fmt_dt


def _set_flash(request: Request, message: str, category: str = "info") -> None:
    request.session["_flash"] = {"message": message, "category": category}


def _render(request: Request, template: str, **context):
    base = {
        "request": request,
        "flash": request.session.pop("_flash", None),
        "Role": Role,
        "Branch": Branch,
        "RoleType": RoleType,
        "CompanyApplicationAction": CompanyApplicationAction,
    }
    base.update(context)
    return templates.TemplateResponse(template, base)


def _redirect(request: Request, route_name: str, message: Optional[str] = None, category: str = "info"):
    if message:
        _set_flash(request, message, category)
    return RedirectResponse(request.url_for(route_name), status_code=303)


def _txt(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _flt(value) -> Optional[float]:
    value = _txt(value)
    return float(value) if value is not None else None


def _int(value) -> Optional[int]:
    value = _txt(value)
    return int(value) if value is not None else None


def _dt(value) -> Optional[datetime]:
    value = _txt(value)
    return to_utc_naive(datetime.fromisoformat(value)) if value else None


def _branches(values: list[str]) -> Optional[list[Branch]]:
    return [Branch(v) for v in values if v] or None


def _ui_user(request: Request, session: Session) -> Optional[User]:
    user_id = request.session.get("ui_user_id")
    if not user_id:
        return None
    user = session.get(User, user_id)
    if not user or not getattr(user, "is_active", True):
        request.session.clear()
        return None
    return user


def _home_for(user: Optional[User]) -> str:
    if not user:
        return "/ui/"
    if user.role == Role.student:
        return "/ui/student"
    if user.role == Role.company:
        return "/ui/company"
    return "/ui/admin"


def _require(request: Request, session: Session, role: Optional[Role] = None, verified_admin: bool = False):
    user = _ui_user(request, session)
    if not user:
        return None, _redirect(request, "ui_login", "Please log in first.", "warning")
    if role and user.role != role:
        return None, _redirect(request, "ui_home", "You do not have access to that page.", "danger")
    if user.role in {Role.company, Role.admin} and not getattr(user, "email_verified", False):
        return None, _redirect(request, "ui_verify_email", "Please verify email first.", "warning")
    if verified_admin and user.role == Role.admin and not user.is_first_admin and not user.verified:
        return None, _redirect(request, "ui_home", "Admin approval is still pending.", "warning")
    return user, None


def _eligible_jobs(session: Session, student: Student) -> list[Job]:
    jobs = crud.list_verified_jobs(session, skip=0, limit=None)
    eligible = []
    for job in jobs:
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
        if get_application_block_reason(session, student.id, getattr(job, "role_type", None)):
            continue
        eligible.append(job)
    return eligible


@router.get("/", name="ui_home")
def home(request: Request):
    with Session(engine) as session:
        user = _ui_user(request, session)
        return _render(request, "home.html", current_user=user, role_home=_home_for(user), jobs=crud.list_verified_jobs(session, 0, 12))


@router.get("/jobs", name="ui_jobs")
def jobs_page(request: Request):
    with Session(engine) as session:
        user = _ui_user(request, session)
        return _render(request, "jobs_list.html", current_user=user, role_home=_home_for(user), jobs=crud.list_verified_jobs(session, 0, 50))


@router.get("/jobs/{job_id}", name="ui_job_detail")
def job_detail(job_id: int, request: Request):
    with Session(engine) as session:
        user = _ui_user(request, session)
        job = crud.get_job_by_id(session, job_id)
        if not job:
            return _redirect(request, "ui_jobs", "Job not found.", "warning")
        return _render(request, "job_detail.html", current_user=user, role_home=_home_for(user), job=job, company=session.get(Company, job.company_id))


@router.get("/login", name="ui_login")
def login_page(request: Request):
    with Session(engine) as session:
        user = _ui_user(request, session)
        if user:
            return RedirectResponse(_home_for(user), status_code=303)
        return _render(request, "auth_login.html", current_user=None, role_home="/ui/")


@router.post("/login", name="ui_login_post")
async def login_submit(request: Request):
    form = await request.form()
    with Session(engine) as session:
        user = crud.authenticate_user(session, str(form.get("email", "")).strip(), str(form.get("password", "")))
        if not user:
            return _redirect(request, "ui_login", "Incorrect credentials.", "danger")
        if user.role in {Role.company, Role.admin} and not getattr(user, "email_verified", False):
            return _redirect(request, "ui_verify_email", "Please verify email first.", "warning")
        if user.role == Role.admin and not user.is_first_admin and not user.verified:
            return _redirect(request, "ui_login", "Admin approval is still pending.", "warning")
        request.session["ui_user_id"] = user.id
        request.session["ui_access_token"] = create_access_token({"sub": str(user.id), "role": user.role})
    return RedirectResponse(_home_for(user), status_code=303)


@router.post("/logout", name="ui_logout")
def logout_submit(request: Request):
    request.session.clear()
    return _redirect(request, "ui_home", "Logged out.", "info")


@router.get("/register", name="ui_register")
def register_page(request: Request):
    with Session(engine) as session:
        return _render(request, "auth_register.html", current_user=_ui_user(request, session), role_home="/ui/")


@router.post("/register", name="ui_register_post")
async def register_submit(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    password = str(form.get("password", ""))
    role = Role(str(form.get("role", Role.company.value)))
    with Session(engine) as session:
        crud.purge_expired_unverified_users(session, older_than_days=15, email=email)
        is_first_admin = role == Role.admin and session.exec(select(User).where(User.role == Role.admin)).first() is None
        try:
            user = crud.create_user(session, email, password, role, is_first_admin=is_first_admin)
        except IntegrityError:
            session.rollback()
            return _redirect(request, "ui_register", "Email already registered.", "danger")
        token = create_email_verification_token(user.id) if role in {Role.admin, Role.company} else None
    if token:
        return _redirect(request, "ui_verify_email", f"Registration successful. Demo verification token: {token}", "success")
    return _redirect(request, "ui_login", "Registration successful.", "success")


@router.get("/verify-email", name="ui_verify_email")
def verify_email_page(request: Request):
    with Session(engine) as session:
        return _render(request, "auth_verify_email.html", current_user=_ui_user(request, session), role_home="/ui/")


@router.post("/verify-email", name="ui_verify_email_post")
async def verify_email_submit(request: Request):
    from .auth import verify_email_verification_token

    form = await request.form()
    user_id = verify_email_verification_token(str(form.get("token", "")).strip())
    if user_id is None:
        return _redirect(request, "ui_verify_email", "Invalid or expired verification token.", "danger")
    with Session(engine) as session:
        if not crud.mark_user_email_verified(session, user_id):
            return _redirect(request, "ui_verify_email", "User not found.", "danger")
    return _redirect(request, "ui_login", "Email verified.", "success")


@router.get("/forgot-password", name="ui_forgot_password")
def forgot_password_page(request: Request):
    with Session(engine) as session:
        return _render(request, "auth_forgot_password.html", current_user=_ui_user(request, session), role_home="/ui/")


@router.post("/forgot-password", name="ui_forgot_password_post")
async def forgot_password_submit(request: Request):
    form = await request.form()
    with Session(engine) as session:
        user = crud.get_user_by_email(session, str(form.get("email", "")).strip())
        token = create_password_reset_token(user.id) if user else None
    return _redirect(request, "ui_reset_password", f"Demo reset token: {token}" if token else "If the account exists, reset instructions were generated.", "info")


@router.get("/reset-password", name="ui_reset_password")
def reset_password_page(request: Request):
    with Session(engine) as session:
        return _render(request, "auth_reset_password.html", current_user=_ui_user(request, session), role_home="/ui/")


@router.post("/reset-password", name="ui_reset_password_post")
async def reset_password_submit(request: Request):
    from .auth import verify_password_reset_token

    form = await request.form()
    user_id = verify_password_reset_token(str(form.get("token", "")).strip())
    if user_id is None:
        return _redirect(request, "ui_reset_password", "Invalid or expired reset token.", "danger")
    with Session(engine) as session:
        if not crud.update_user_password(session, user_id, str(form.get("new_password", ""))):
            return _redirect(request, "ui_reset_password", "User not found.", "danger")
    return _redirect(request, "ui_login", "Password updated.", "success")


@router.get("/student", name="ui_student_dashboard")
def student_dashboard(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        applications = crud.list_student_application_summaries(session, student.id, 0, 5) if student else []
        offers = crud.list_student_offer_summaries(session, student.id, OfferStatus.offered) if student else []
        return _render(request, "student_dashboard.html", current_user=user, role_home=_home_for(user), student=student, applications=applications, offers=offers)


@router.get("/student/profile", name="ui_student_profile")
def student_profile_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        return _render(request, "student_profile.html", current_user=user, role_home=_home_for(user), student=crud.get_student_by_user_id(session, user.id))


@router.post("/student/profile", name="ui_student_profile_post")
async def student_profile_submit(request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        if not student:
            return _redirect(request, "ui_student_profile", "Student profile not found.", "danger")
        updated = crud.update_student(
            session,
            student.id,
            phone=_txt(form.get("phone")),
            personal_email=_txt(form.get("personal_email")),
            address=_txt(form.get("address")),
            resume_url=_txt(form.get("resume_url")),
            github_url=_txt(form.get("github_url")),
            linkedin_url=_txt(form.get("linkedin_url")),
            leetcode_url=_txt(form.get("leetcode_url")),
            codeforces_url=_txt(form.get("codeforces_url")),
            hackerrank_url=_txt(form.get("hackerrank_url")),
            portfolio_url=_txt(form.get("portfolio_url")),
            other_coding_url=_txt(form.get("other_coding_url")),
        )
        if not updated:
            return _redirect(request, "ui_student_profile", "Could not update profile.", "danger")
    return _redirect(request, "ui_student_profile", "Profile updated.", "success")


@router.post("/student/delete", name="ui_student_delete")
def student_delete_submit(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        if not student or not crud.delete_student(session, student.id):
            return _redirect(request, "ui_student_profile", "Could not deactivate student profile.", "danger")
    request.session.clear()
    return _redirect(request, "ui_home", "Student profile deactivated.", "info")


@router.get("/student/jobs", name="ui_student_jobs")
def student_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        if not student:
            return _redirect(request, "ui_student_dashboard", "Student profile not found.", "danger")
        return _render(request, "student_jobs.html", current_user=user, role_home=_home_for(user), student=student, jobs=_eligible_jobs(session, student))


@router.post("/student/jobs/{job_id}/apply", name="ui_student_apply")
def student_apply_submit(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        if not student:
            return _redirect(request, "ui_student_jobs", "Student profile not found.", "danger")
        try:
            crud.apply_job(session, student.id, job_id)
        except ValueError as exc:
            return _redirect(request, "ui_student_jobs", str(exc), "warning")
    return _redirect(request, "ui_student_applications", "Application submitted.", "success")


@router.get("/student/applications", name="ui_student_applications")
def student_applications_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        items = crud.list_student_application_summaries(session, student.id, 0, 50) if student else []
        return _render(request, "student_applications.html", current_user=user, role_home=_home_for(user), applications=items)


@router.get("/student/offers", name="ui_student_offers")
def student_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        offered = crud.list_student_offer_summaries(session, student.id, OfferStatus.offered) if student else []
        accepted = crud.list_student_offer_summaries(session, student.id, OfferStatus.accepted) if student else []
        return _render(request, "student_offers.html", current_user=user, role_home=_home_for(user), offered=offered, accepted=accepted)


@router.post("/student/offers/{offer_id}/accept", name="ui_student_offer_accept")
def student_accept_offer(offer_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        if not student or not crud.accept_offer(session, offer_id, student.id):
            return _redirect(request, "ui_student_offers", "Could not accept offer.", "warning")
    return _redirect(request, "ui_student_offers", "Offer accepted.", "success")


@router.post("/student/offers/{offer_id}/decline", name="ui_student_offer_decline")
def student_decline_offer(offer_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.student)
        if redirect:
            return redirect
        student = crud.get_student_by_user_id(session, user.id)
        if not student or not crud.decline_offer(session, offer_id, student.id):
            return _redirect(request, "ui_student_offers", "Could not decline offer.", "warning")
    return _redirect(request, "ui_student_offers", "Offer declined.", "info")


@router.get("/company", name="ui_company_dashboard")
def company_dashboard(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        jobs = crud.list_company_jobs(session, company.id, 0, 5) if company else []
        offers = crud.list_company_accepted_offer_summaries(session, company.id, 0, 5) if company else []
        return _render(request, "company_dashboard.html", current_user=user, role_home=_home_for(user), company=company, jobs=jobs, offers=offers)


@router.get("/company/profile", name="ui_company_profile")
def company_profile_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        return _render(request, "company_profile.html", current_user=user, role_home=_home_for(user), company=crud.get_company_by_user_id(session, user.id))


@router.post("/company/profile", name="ui_company_profile_post")
async def company_profile_submit(request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        if crud.get_company_by_user_id(session, user.id):
            return _redirect(request, "ui_company_profile", "Company profile already exists.", "warning")
        try:
            crud.create_company(session, user.id, str(form.get("name", "")).strip())
        except IntegrityError:
            session.rollback()
            return _redirect(request, "ui_company_profile", "Could not create company profile.", "danger")
    return _redirect(request, "ui_company_profile", "Company profile created.", "success")


@router.post("/company/delete", name="ui_company_delete")
def company_delete_submit(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        if not company or not crud.delete_company(session, company.id):
            return _redirect(request, "ui_company_profile", "Could not deactivate company.", "danger")
    request.session.clear()
    return _redirect(request, "ui_home", "Company deactivated.", "info")


@router.get("/company/jobs", name="ui_company_jobs")
def company_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        jobs = crud.list_company_jobs(session, company.id, 0, 50) if company else []
        return _render(request, "company_jobs.html", current_user=user, role_home=_home_for(user), company=company, jobs=jobs)


@router.post("/company/jobs", name="ui_company_jobs_post")
async def company_jobs_submit(request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        if not company:
            return _redirect(request, "ui_company_profile", "Create your company profile first.", "warning")
        try:
            crud.create_job(
                session,
                company.id,
                title=str(form.get("title", "")).strip(),
                description=_txt(form.get("description")),
                min_cgpa=_flt(form.get("min_cgpa")),
                allowed_branches=_branches(list(form.getlist("allowed_branches"))),
                max_backlogs=_int(form.get("max_backlogs")),
                role_type=str(form.get("role_type", RoleType.full_time.value)),
                internship_duration=_txt(form.get("internship_duration")),
                stipend=_flt(form.get("stipend")),
                ctc=_flt(form.get("ctc")),
                ppo_available=str(form.get("ppo_available", "")) == "on",
                application_deadline=_dt(form.get("application_deadline")),
            )
        except ValueError as exc:
            return _redirect(request, "ui_company_jobs", str(exc), "warning")
    return _redirect(request, "ui_company_jobs", "Job created.", "success")


@router.post("/company/jobs/{job_id}/delete", name="ui_company_job_delete")
def company_job_delete_submit(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        job = session.get(Job, job_id)
        if not company or not job or job.company_id != company.id:
            return _redirect(request, "ui_company_jobs", "Job not found.", "warning")
        try:
            ok = crud.delete_job(session, job_id)
        except ValueError as exc:
            return _redirect(request, "ui_company_jobs", str(exc), "warning")
        if not ok:
            return _redirect(request, "ui_company_jobs", "Could not delete job.", "danger")
    return _redirect(request, "ui_company_jobs", "Job deleted.", "info")


@router.get("/company/jobs/{job_id}/applicants", name="ui_company_applicants")
def company_applicants_page(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        job = session.get(Job, job_id)
        if not company or not job or job.company_id != company.id:
            return _redirect(request, "ui_company_jobs", "Not allowed to view applicants for that job.", "warning")
        applicants = crud.list_company_applicant_summaries(session, job_id, 0, 100)
        return _render(request, "company_applicants.html", current_user=user, role_home=_home_for(user), job=job, applicants=applicants)


@router.post("/company/applications/{application_id}", name="ui_company_application_action")
async def company_application_action_submit(application_id: int, request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        application = session.get(Application, application_id)
        if not company or not application:
            return _redirect(request, "ui_company_jobs", "Application not found.", "warning")
        job = session.get(Job, application.job_id)
        if not job or job.company_id != company.id:
            return _redirect(request, "ui_company_jobs", "Not allowed to modify this application.", "danger")
        try:
            crud.apply_company_action(
                session,
                application,
                job,
                company.id,
                CompanyApplicationAction(str(form.get("status", CompanyApplicationAction.shortlisted.value))),
                _flt(form.get("ctc")),
                _dt(form.get("offer_response_deadline")),
            )
        except ValueError as exc:
            _set_flash(request, str(exc), "warning")
            return RedirectResponse(f"/ui/company/jobs/{job.id}/applicants", status_code=303)
    _set_flash(request, "Application updated.", "success")
    return RedirectResponse(f"/ui/company/jobs/{job.id}/applicants", status_code=303)


@router.get("/company/offers", name="ui_company_offers")
def company_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.company)
        if redirect:
            return redirect
        company = crud.get_company_by_user_id(session, user.id)
        offers = crud.list_company_accepted_offer_summaries(session, company.id, 0, 100) if company else []
        return _render(request, "company_offers.html", current_user=user, role_home=_home_for(user), offers=offers)


@router.get("/admin", name="ui_admin_dashboard")
def admin_dashboard(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        stats = {
            "total_students": crud.count_students(session),
            "placed_students": crud.count_placed_students(session),
            "active_jobs": crud.count_active_jobs(session),
            "total_jobs": crud.count_jobs(session),
            "total_companies": crud.count_companies(session, verified=True),
            "pending_companies": crud.count_companies(session, verified=False),
            "pending_admins": crud.count_pending_admins(session),
            "offers_made": crud.count_offers_made(session),
            "offers_pending_response": crud.count_offers_pending_response(session),
            "offers_accepted": crud.count_offers_accepted(session),
            "branch_stats": crud.get_branch_placement_stats(session),
        }
        return _render(request, "admin_dashboard.html", current_user=user, role_home=_home_for(user), stats=stats)


@router.get("/admin/users", name="ui_admin_users")
def admin_users_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return _render(request, "admin_users.html", current_user=user, role_home=_home_for(user), users=crud.get_all_users(session, 0, 100))


@router.get("/admin/users/{user_id}", name="ui_admin_user_detail")
def admin_user_detail_page(user_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        detail = crud.get_user_by_id(session, user_id)
        if not detail:
            return _redirect(request, "ui_admin_users", "User not found.", "warning")
        return _render(request, "admin_user_detail.html", current_user=user, role_home=_home_for(user), user_detail=detail)


@router.get("/admin/pending-admins", name="ui_admin_pending_admins")
def admin_pending_admins_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not user.is_first_admin:
            return _redirect(request, "ui_admin_dashboard", "Only the first admin can verify pending admins.", "warning")
        return _render(request, "admin_pending_admins.html", current_user=user, role_home=_home_for(user), pending_admins=crud.get_pending_admins(session, 0, 100))


@router.post("/admin/users/{user_id}/verify-admin", name="ui_admin_verify_admin")
def admin_verify_admin_submit(user_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not user.is_first_admin:
            return _redirect(request, "ui_admin_dashboard", "Only the first admin can verify admins.", "warning")
        if not crud.verify_admin(session, user_id, user.id):
            return _redirect(request, "ui_admin_pending_admins", "Could not verify admin.", "danger")
    return _redirect(request, "ui_admin_pending_admins", "Admin verified.", "success")


@router.get("/admin/students", name="ui_admin_students")
def admin_students_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return _render(request, "admin_students.html", current_user=user, role_home=_home_for(user), students=crud.list_students(session, 0, 100, include_inactive=True))


@router.post("/admin/students/provision", name="ui_admin_students_provision")
async def admin_students_provision_submit(request: Request):
    form = await request.form()
    email = str(form.get("email", "")).strip()
    reg_no = str(form.get("reg_no", "")).strip()
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        crud.purge_expired_unverified_users(session, older_than_days=15, email=email)
        if crud.get_user_by_email(session, email):
            return _redirect(request, "ui_admin_students", "Email already registered.", "warning")
        if session.exec(select(Student).where(Student.reg_no == reg_no)).first():
            return _redirect(request, "ui_admin_students", "Registration number already exists.", "warning")
        temp_password = secrets.token_urlsafe(24)
        try:
            new_user = User(
                email=email,
                password_hash=hash_password(temp_password),
                role=Role.student,
                email_verified=False,
                is_first_admin=False,
                verified=False,
                is_active=True,
            )
            session.add(new_user)
            session.flush()
            student = Student(
                user_id=new_user.id,
                name=str(form.get("name", "")).strip(),
                reg_no=reg_no,
                roll_no=str(form.get("roll_no", "")).strip(),
                cgpa=float(form.get("cgpa", "0")),
                branch=Branch(str(form.get("branch", Branch.CSE.value))),
                graduation_year=int(form.get("graduation_year", "2026")),
                backlogs=int(form.get("backlogs", "0")),
            )
            session.add(student)
            session.commit()
        except Exception:
            session.rollback()
            return _redirect(request, "ui_admin_students", "Could not provision student.", "danger")
    return _redirect(request, "ui_admin_students", f"Student provisioned. Demo invite token: {create_password_reset_token(new_user.id)}", "success")


@router.get("/admin/students/{student_id}", name="ui_admin_student_edit")
def admin_student_edit_page(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        student = session.get(Student, student_id)
        if not student:
            return _redirect(request, "ui_admin_students", "Student not found.", "warning")
        return _render(request, "admin_student_edit.html", current_user=user, role_home=_home_for(user), student=student)


@router.post("/admin/students/{student_id}", name="ui_admin_student_edit_post")
async def admin_student_edit_submit(student_id: int, request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        updated = crud.update_student(
            session,
            student_id,
            reg_no=_txt(form.get("reg_no")),
            roll_no=_txt(form.get("roll_no")),
            cgpa=_flt(form.get("cgpa")),
            branch=Branch(str(form.get("branch", Branch.CSE.value))),
            graduation_year=_int(form.get("graduation_year")),
            backlogs=_int(form.get("backlogs")),
        )
        if not updated:
            _set_flash(request, "Could not update student.", "danger")
            return RedirectResponse(f"/ui/admin/students/{student_id}", status_code=303)
    return _redirect(request, "ui_admin_students", "Student updated.", "success")


@router.post("/admin/students/{student_id}/delete", name="ui_admin_student_delete")
def admin_student_delete_submit(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_student(session, student_id):
            return _redirect(request, "ui_admin_students", "Could not deactivate student.", "danger")
    return _redirect(request, "ui_admin_students", "Student deactivated.", "info")


@router.post("/admin/students/{student_id}/reactivate", name="ui_admin_student_reactivate")
def admin_student_reactivate_submit(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.reactivate_student(session, student_id):
            return _redirect(request, "ui_admin_students", "Could not reactivate student.", "danger")
    return _redirect(request, "ui_admin_students", "Student reactivated.", "success")


@router.get("/admin/companies", name="ui_admin_companies")
def admin_companies_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return _render(request, "admin_companies.html", current_user=user, role_home=_home_for(user), companies=crud.list_companies(session, 0, 100, include_inactive=True))


@router.post("/admin/companies/{company_id}/verify", name="ui_admin_company_verify")
def admin_company_verify_submit(company_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.verify_company(session, company_id):
            return _redirect(request, "ui_admin_companies", "Could not verify company.", "danger")
    return _redirect(request, "ui_admin_companies", "Company verified.", "success")


@router.post("/admin/companies/{company_id}/delete", name="ui_admin_company_delete")
def admin_company_delete_submit(company_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_company(session, company_id):
            return _redirect(request, "ui_admin_companies", "Could not deactivate company.", "danger")
    return _redirect(request, "ui_admin_companies", "Company deactivated.", "info")


@router.post("/admin/companies/{company_id}/reactivate", name="ui_admin_company_reactivate")
def admin_company_reactivate_submit(company_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.reactivate_company(session, company_id):
            return _redirect(request, "ui_admin_companies", "Could not reactivate company.", "danger")
    return _redirect(request, "ui_admin_companies", "Company reactivated.", "success")


@router.get("/admin/jobs", name="ui_admin_jobs")
def admin_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return _render(request, "admin_jobs.html", current_user=user, role_home=_home_for(user), jobs=crud.list_jobs(session, 0, 100))


@router.post("/admin/jobs/{job_id}/close", name="ui_admin_job_close")
def admin_job_close_submit(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        try:
            crud.close_job(session, job_id)
        except ValueError as exc:
            return _redirect(request, "ui_admin_jobs", str(exc), "warning")
    return _redirect(request, "ui_admin_jobs", "Job closed.", "info")


@router.post("/admin/jobs/{job_id}/delete", name="ui_admin_job_delete")
def admin_job_delete_submit(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        try:
            ok = crud.delete_job(session, job_id)
        except ValueError as exc:
            return _redirect(request, "ui_admin_jobs", str(exc), "warning")
        if not ok:
            return _redirect(request, "ui_admin_jobs", "Could not delete job.", "danger")
    return _redirect(request, "ui_admin_jobs", "Job deleted.", "info")


@router.get("/admin/applications", name="ui_admin_applications")
def admin_applications_page(request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return _render(request, "admin_applications.html", current_user=user, role_home=_home_for(user), applications=crud.list_applications(session, 0, 100))


@router.post("/admin/applications/{application_id}/delete", name="ui_admin_application_delete")
def admin_application_delete_submit(application_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = _require(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_application(session, application_id):
            return _redirect(request, "ui_admin_applications", "Could not delete application.", "danger")
    return _redirect(request, "ui_admin_applications", "Application deleted.", "info")
