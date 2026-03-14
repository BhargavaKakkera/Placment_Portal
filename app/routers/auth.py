from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from ..database import get_session, serialize_first_admin_registration
from .. import crud
from ..config import DEBUG
from ..schemas import (
    RegisterIn,
    RegisterOut,
    Token,
    PasswordResetRequestIn,
    PasswordResetConfirmIn,
    EmailVerificationConfirmIn,
    EmailVerificationRequestIn,
)
from ..auth import (
    create_access_token,
    create_password_reset_token,
    create_email_verification_token,
    verify_password_reset_token,
    verify_email_verification_token,
)
from ..models import User
from ..enums import Role

router = APIRouter(prefix="/auth", tags=["auth"])
DEBUG_MODE = DEBUG


def _send_password_reset_email(email: str, token: str) -> None:
    """
    Demo background task.
    Replace with real provider integration later.
    """
    # Dev placeholder only: keep logs token-free.
    print(f"[password-reset] queued email for {email}")


def _send_email_verification_email(email: str, token: str) -> None:
    """
    Demo background task.
    Replace with real provider integration later.
    """
    print(f"[email-verification] queued email for {email}")


@router.post("/register", response_model=RegisterOut)
def register(
    payload: RegisterIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    if payload.role == Role.student:
        raise HTTPException(
            status_code=403,
            detail="Student self-registration is disabled. Contact admin for invite."
        )

    is_first_admin = False
    try:
        # Auto-clean stale unverified accounts so email can be reused.
        crud.purge_expired_unverified_users(session, older_than_days=15, email=payload.email)

        # Serialize admin bootstrap so concurrent registrations don't create two first admins.
        if payload.role == Role.admin:
            serialize_first_admin_registration(session)
            existing_admin = session.exec(
                select(User).where(User.role == Role.admin)
            ).first()
            is_first_admin = existing_admin is None

        existing = session.exec(select(User).where(User.email == payload.email)).first()
        if existing:
            if not getattr(existing, "is_active", True):
                raise HTTPException(status_code=409, detail="Account exists but is deactivated")
            raise HTTPException(status_code=409, detail="Email already registered")

        user = crud.create_user(
            session,
            payload.email,
            payload.password,
            payload.role,
            is_first_admin=is_first_admin
        )
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")

    verification_token = None
    if payload.role in (Role.admin, Role.company):
        verification_token = create_email_verification_token(user.id)
        background_tasks.add_task(
            _send_email_verification_email,
            user.email,
            verification_token,
        )

    response = {
        "message": "Registration successful. Verify your email before logging in.",
        "email_verification_sent": verification_token is not None,
    }
    if DEBUG_MODE:
        response["verification_token"] = verification_token
    return response


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user_by_email = session.exec(select(User).where(User.email == form_data.username)).first()
    if user_by_email and not getattr(user_by_email, "is_active", True):
        raise HTTPException(status_code=403, detail="Account is deactivated")

    user = crud.authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect credentials")

    if user.role in (Role.admin, Role.company) and not getattr(user, "email_verified", False):
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please verify your email first."
        )
    
    # Check if admin needs verification
    if user.role == Role.admin:
        # First admin is always verified
        if not user.is_first_admin and not user.verified:
            raise HTTPException(
                status_code=403, 
                detail="Admin not verified. Please wait for approval from first admin."
            )
    
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"access_token": token}


@router.post("/verify-email")
def verify_email(payload: EmailVerificationConfirmIn, session: Session = Depends(get_session)):
    """Verify a user's email using a valid verification token."""
    user_id = verify_email_verification_token(payload.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user = crud.mark_user_email_verified(session, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="User not found or inactive")

    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
def resend_verification_email(
    payload: EmailVerificationRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """Resend email verification instructions for self-registered company/admin users."""
    user = crud.get_user_by_email(session, payload.email)
    verification_token = None

    if user and user.role in (Role.admin, Role.company) and not getattr(user, "email_verified", False):
        verification_token = create_email_verification_token(user.id)
        background_tasks.add_task(_send_email_verification_email, user.email, verification_token)

    response = {
        "message": "If the account exists and still needs verification, verification instructions have been queued.",
    }
    if DEBUG_MODE:
        response["verification_token"] = verification_token
    return response


@router.post("/forgot-password")
def forgot_password(
    payload: PasswordResetRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Request password reset.
    Uses a background task to simulate sending reset instructions.
    """
    user = crud.get_user_by_email(session, payload.email)
    reset_token = None

    if user:
        reset_token = create_password_reset_token(user.id)
        background_tasks.add_task(_send_password_reset_email, user.email, reset_token)

    # Keep response generic. Expose token only in explicit debug mode.
    response = {
        "message": "If the account exists, reset instructions have been queued.",
    }
    if DEBUG_MODE:
        response["reset_token"] = reset_token
    return response


@router.post("/reset-password")
def reset_password(payload: PasswordResetConfirmIn, session: Session = Depends(get_session)):
    """Reset password using a valid reset token."""
    user_id = verify_password_reset_token(payload.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user = crud.update_user_password(session, user_id, payload.new_password)
    if not user:
        raise HTTPException(status_code=400, detail="User not found or inactive")

    return {"message": "Password reset successful"}
