from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .. import crud
from ..auth import create_access_token, create_email_verification_token, create_password_reset_token
from ..config import DEBUG, ENABLE_RATE_LIMITING, MAX_PASSWORD_RESET_ATTEMPTS, PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS
from ..database import engine
from ..email_service import send_email_verification_email, send_password_reset_email
from ..enums import Role, RoleType
from ..models import Company, User
from ..schemas import EmailVerificationConfirmIn, PasswordResetConfirmIn, PasswordResetRequestIn, RegisterIn
from ..rate_limiter import check_rate_limit, record_attempt, reset_limit
from ..crud.token_crud import mark_token_as_used
from .helpers import build_pager, current_user, extract_field_errors, home_for, is_public_job_visible, parse_page_limit, read_form_with_csrf, redirect_to, render, validation_message

router = APIRouter()
DEBUG_MODE = DEBUG


@router.get("/", name="ui_home")
def home(request: Request):
    with Session(engine) as session:
        user = current_user(request, session)
        page, limit, skip = parse_page_limit(request, default_limit=12, max_limit=50)
        job_search = str(request.query_params.get("q", "")).strip()
        jobs = crud.list_verified_jobs(session, skip, limit, search=job_search or None)
        total = crud.count_verified_jobs(session, search=job_search or None)
        companies_by_id = {company.id: company for company in crud.list_companies(session, 0, 1000, include_inactive=True)}
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "home.html",
            current_user=user,
            role_home=home_for(user),
            jobs=jobs,
            companies_by_id=companies_by_id,
            pager=pager,
            job_search=job_search,
        )


@router.get("/jobs", name="ui_jobs")
def jobs_page(request: Request):
    with Session(engine) as session:
        user = current_user(request, session)
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        job_search = str(request.query_params.get("q", "")).strip()
        role_raw = str(request.query_params.get("role_type", "")).strip()
        role_filter = None
        if role_raw:
            try:
                role_filter = RoleType(role_raw)
            except ValueError:
                role_filter = None
        jobs = crud.list_verified_jobs(session, skip, limit, search=job_search or None, role_type=role_filter)
        total = crud.count_verified_jobs(session, search=job_search or None, role_type=role_filter)
        companies_by_id = {company.id: company for company in crud.list_companies(session, 0, 1000, include_inactive=True)}
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "jobs_list.html",
            current_user=user,
            role_home=home_for(user),
            jobs=jobs,
            companies_by_id=companies_by_id,
            pager=pager,
            job_search=job_search,
            role_filter=role_raw,
        )


@router.get("/jobs/{job_id}", name="ui_job_detail")
def job_detail(job_id: int, request: Request):
    with Session(engine) as session:
        user = current_user(request, session)
        job = crud.get_job_by_id(session, job_id)
        if not is_public_job_visible(session, job):
            return redirect_to(request, "ui_jobs", "Job not found.", "warning")
        return render(request, "job_detail.html", current_user=user, role_home=home_for(user), job=job, company=session.get(Company, job.company_id))


@router.get("/login", name="ui_login")
def login_page(request: Request):
    with Session(engine) as session:
        user = current_user(request, session)
        if user:
            return RedirectResponse(home_for(user), status_code=303)
        return render(
            request,
            "auth_login.html",
            current_user=None,
            role_home="/ui/",
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/login", name="ui_login_post")
async def login_submit(request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_login", str(exc), "warning")
    form_data = {
        "email": str(form.get("email", "")).strip(),
    }
    with Session(engine) as session:
        user = crud.authenticate_user(session, form_data["email"], str(form.get("password", "")))
        if not user:
            return render(
                request,
                "auth_login.html",
                current_user=None,
                role_home="/ui/",
                form_data=form_data,
                field_errors={"email": "Invalid email or password.", "password": "Invalid email or password."},
                error_message="Invalid email or password.",
            )
        if user.role in {Role.company, Role.admin} and not getattr(user, "email_verified", False):
            return redirect_to(request, "ui_verify_email", "Please verify email first.", "warning")
        if user.role == Role.admin and not user.is_first_admin and not user.verified:
            return redirect_to(request, "ui_login", "Admin approval is still pending.", "warning")
        request.session.clear()
        request.session["ui_user_id"] = user.id
        request.session["ui_access_token"] = create_access_token({"sub": str(user.id), "role": user.role})
    return RedirectResponse(home_for(user), status_code=303)


@router.post("/logout", name="ui_logout")
async def logout_submit(request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_home", str(exc), "warning")
    request.session.clear()
    return redirect_to(request, "ui_home", "Logged out.", "info")


@router.get("/register", name="ui_register")
def register_page(request: Request):
    with Session(engine) as session:
        return render(
            request,
            "auth_register.html",
            current_user=current_user(request, session),
            role_home="/ui/",
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/register", name="ui_register_post")
async def register_submit(request: Request, background_tasks: BackgroundTasks):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_register", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "email": str(form.get("email", "")).strip(),
        "password": str(form.get("password", "")),
        "role": str(form.get("role", Role.company.value)),
    }
    
    try:
        payload = RegisterIn.model_validate(form_data)
    except ValidationError as exc:
        with Session(engine) as session:
            user = current_user(request, session)
        field_errors = extract_field_errors(exc)
        return render(
            request,
            "auth_register.html",
            current_user=user,
            role_home="/ui/",
            form_data=form_data,
            field_errors=field_errors,
            error_message=validation_message(exc),
        )
    email = payload.email
    password = payload.password
    role = payload.role
    if role == Role.student:
        with Session(engine) as session:
            user = current_user(request, session)
        return render(
            request,
            "auth_register.html",
            current_user=user,
            role_home="/ui/",
            form_data=form_data,
            field_errors={},
            error_message="Student self-registration is disabled.",
        )
    with Session(engine) as session:
        crud.purge_expired_unverified_users(session, older_than_days=15, email=email)
        is_first_admin = role == Role.admin and session.exec(select(User).where(User.role == Role.admin)).first() is None
        try:
            user = crud.create_user(session, email, password, role, is_first_admin=is_first_admin)
        except IntegrityError:
            session.rollback()
            user = current_user(request, session)
            return render(
                request,
                "auth_register.html",
                current_user=user,
                role_home="/ui/",
                form_data=form_data,
                field_errors={},
                error_message="Email already registered.",
            )
        token = create_email_verification_token(user.id) if role in {Role.admin, Role.company} else None
    if token:
        background_tasks.add_task(send_email_verification_email, str(email), token)
    if token and DEBUG_MODE:
        return redirect_to(
            request,
            "ui_verify_email",
            f"Registration successful. Demo verification token: {token}",
            "success",
        )
    if token:
        return redirect_to(
            request,
            "ui_verify_email",
            "Registration successful. Verification instructions generated.",
            "success",
        )
    return redirect_to(request, "ui_login", "Registration successful.", "success")


@router.get("/verify-email", name="ui_verify_email")
def verify_email_page(request: Request):
    with Session(engine) as session:
        return render(
            request,
            "auth_verify_email.html",
            current_user=current_user(request, session),
            role_home="/ui/",
            token=str(request.query_params.get("token", "")),
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/verify-email", name="ui_verify_email_post")
async def verify_email_submit(request: Request):
    from ..auth import verify_email_verification_token

    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_verify_email", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "token": str(form.get("token", "")).strip(),
    }
    
    try:
        payload = EmailVerificationConfirmIn.model_validate(form_data)
    except ValidationError as exc:
        with Session(engine) as session:
            user = current_user(request, session)
        field_errors = extract_field_errors(exc)
        return render(
            request,
            "auth_verify_email.html",
            current_user=user,
            role_home="/ui/",
            form_data=form_data,
            field_errors=field_errors,
            error_message=validation_message(exc),
        )
    with Session(engine) as session:
        user_id = verify_email_verification_token(payload.token, session=session)
        if user_id is None:
            user = current_user(request, session)
            return render(
                request,
                "auth_verify_email.html",
                current_user=user,
                role_home="/ui/",
                form_data=form_data,
                field_errors={},
                error_message="Invalid or expired verification token.",
            )
        if not crud.mark_user_email_verified(session, user_id):
            user = current_user(request, session)
            return render(
                request,
                "auth_verify_email.html",
                current_user=user,
                role_home="/ui/",
                form_data=form_data,
                field_errors={},
                error_message="User not found.",
            )
        # Mark token as consumed
        mark_token_as_used(session, payload.token, user_id, "email_verification")
    if DEBUG_MODE:
        return redirect_to(request, "ui_login", f"Email verified. (Debug token already consumed)", "success")
    return redirect_to(request, "ui_login", "Email verified.", "success")


@router.get("/forgot-password", name="ui_forgot_password")
def forgot_password_page(request: Request):
    with Session(engine) as session:
        return render(
            request,
            "auth_forgot_password.html",
            current_user=current_user(request, session),
            role_home="/ui/",
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/forgot-password", name="ui_forgot_password_post")
async def forgot_password_submit(request: Request, background_tasks: BackgroundTasks):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_forgot_password", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "email": str(form.get("email", "")).strip(),
    }
    
    try:
        payload = PasswordResetRequestIn.model_validate(form_data)
    except ValidationError as exc:
        with Session(engine) as session:
            user = current_user(request, session)
        field_errors = extract_field_errors(exc)
        return render(
            request,
            "auth_forgot_password.html",
            current_user=user,
            role_home="/ui/",
            form_data=form_data,
            field_errors=field_errors,
            error_message=validation_message(exc),
        )
    
    # Rate limiting per email
    if ENABLE_RATE_LIMITING:
        allowed, remaining = check_rate_limit(
            f"password_reset:{payload.email}",
            max_attempts=MAX_PASSWORD_RESET_ATTEMPTS,
            window_seconds=PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS
        )
        if not allowed:
            with Session(engine) as session:
                user = current_user(request, session)
            return render(
                request,
                "auth_forgot_password.html",
                current_user=user,
                role_home="/ui/",
                form_data=form_data,
                field_errors={},
                error_message="Too many password reset attempts. Try again later.",
            )
        record_attempt(f"password_reset:{payload.email}", count=1)
    
    with Session(engine) as session:
        user = crud.get_user_by_email(session, payload.email)
        token = create_password_reset_token(user.id) if user else None
    if token:
        background_tasks.add_task(send_password_reset_email, payload.email, token)
        if ENABLE_RATE_LIMITING:
            reset_limit(f"password_reset:{payload.email}")
    if token and DEBUG_MODE:
        return redirect_to(request, "ui_reset_password", f"Demo reset token: {token}", "info")
    return redirect_to(
        request,
        "ui_reset_password",
        "If the account exists, reset instructions were generated.",
        "info",
    )


@router.get("/reset-password", name="ui_reset_password")
def reset_password_page(request: Request):
    with Session(engine) as session:
        return render(
            request,
            "auth_reset_password.html",
            current_user=current_user(request, session),
            role_home="/ui/",
            token=str(request.query_params.get("token", "")),
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/reset-password", name="ui_reset_password_post")
async def reset_password_submit(request: Request):
    from ..auth import verify_password_reset_token

    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_reset_password", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "token": str(form.get("token", "")).strip(),
        "new_password": str(form.get("new_password", "")),
    }
    
    try:
        payload = PasswordResetConfirmIn.model_validate(form_data)
    except ValidationError as exc:
        with Session(engine) as session:
            user = current_user(request, session)
        field_errors = extract_field_errors(exc)
        return render(
            request,
            "auth_reset_password.html",
            current_user=user,
            role_home="/ui/",
            form_data=form_data,
            field_errors=field_errors,
            error_message=validation_message(exc),
        )
    with Session(engine) as session:
        user_id = verify_password_reset_token(payload.token, session=session)
        if user_id is None:
            user = current_user(request, session)
            return render(
                request,
                "auth_reset_password.html",
                current_user=user,
                role_home="/ui/",
                form_data=form_data,
                field_errors={},
                error_message="Invalid or expired reset token.",
            )
        if not crud.update_user_password(session, user_id, payload.new_password):
            user = current_user(request, session)
            return render(
                request,
                "auth_reset_password.html",
                current_user=user,
                role_home="/ui/",
                form_data=form_data,
                field_errors={},
                error_message="User not found.",
            )
        # Mark token as consumed
        mark_token_as_used(session, payload.token, user_id, "password_reset")
    if DEBUG_MODE:
        return redirect_to(request, "ui_login", "Password updated. (Debug token already consumed)", "success")
    return redirect_to(request, "ui_login", "Password updated.", "success")
