import time
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..database import get_session, serialize_first_admin_registration
from .. import crud
from ..config import (
    DEBUG, ENABLE_RATE_LIMITING, 
    MAX_LOGIN_ATTEMPTS, LOGIN_ATTEMPT_WINDOW_SECONDS,
    MAX_PASSWORD_RESET_ATTEMPTS, PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS,
    MAX_EMAIL_VERIFICATION_RESEND, EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS,
    EXPOSE_TOKENS_IN_RESPONSES,
    email_runtime_config_summary,
)
from ..schemas import (
    RegisterIn,
    RegisterOut,
    Token,
    PasswordResetRequestIn,
    PasswordResetConfirmIn,
    EmailVerificationConfirmIn,
    EmailVerificationRequestIn,
    ChangePasswordIn,
)
from ..auth import (
    create_access_token,
    create_password_reset_token,
    create_email_verification_token,
    verify_password_reset_token,
    verify_email_verification_token,
    get_current_user,
    verify_password,
)
from ..models import User
from ..enums import Role
from ..exceptions import ConflictError, AuthenticationError, TokenError, DatabaseError, EmailSendError
from ..rate_limiter import check_rate_limit, record_attempt, reset_limit
from ..logger import get_logger
from ..email_service import send_email_verification_email, send_password_reset_email
from ..security_alerts import record_auth_failure
from ..crud.token_crud import mark_token_as_used

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _send_password_reset_email(email: str, token: str) -> None:
    logger.info("Password reset background task begins execution for %s", email)
    try:
        send_password_reset_email(email, token)
    except EmailSendError as exc:
        logger.exception("Password reset email failed for %s: %s", email, exc.message)
        raise
    except Exception:
        logger.exception("Unexpected password reset background task failure for %s", email)
        raise
    logger.info("Password reset background task completed for %s", email)


def _send_email_verification_email(email: str, token: str) -> None:
    logger.info("Background task begins execution: email verification for %s", email)
    try:
        send_email_verification_email(email, token)
    except EmailSendError as exc:
        logger.exception("Verification email failed for %s: %s", email, exc.message)
        raise
    except Exception:
        logger.exception("Unexpected verification email background task failure for %s", email)
        raise
    logger.info("Background task completed: email verification for %s", email)


@router.post("/register", response_model=RegisterOut)
def register(
    payload: RegisterIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    try:
        logger.info(
            "Registration starts for role=%s email=%s email_config=%s",
            payload.role,
            payload.email,
            email_runtime_config_summary(),
        )

        if payload.role == Role.student:
            logger.warning(f"Student self-registration blocked for: {payload.email}")
            raise ConflictError("Student self-registration is disabled. Contact admin for invite.")

        is_first_admin = False
        try:
            crud.purge_expired_unverified_users(session, older_than_days=15, email=payload.email)
            logger.debug(f"Cleaned expired unverified users for: {payload.email}")

            if payload.role == Role.admin:
                serialize_first_admin_registration(session)
                existing_admin = session.exec(
                    select(User).where(User.role == Role.admin)
                ).first()
                is_first_admin = existing_admin is None
                logger.debug(f"First admin check: {is_first_admin}")

            existing = session.exec(select(User).where(User.email == payload.email)).first()
            if existing:
                if not getattr(existing, "is_active", True):
                    logger.warning(f"Registration blocked - account deactivated: {payload.email}")
                    raise ConflictError("Account exists but is deactivated")
                logger.warning(f"Registration blocked - email already registered: {payload.email}")
                raise ConflictError("Email already registered")

            user = crud.create_user(
                session,
                payload.email,
                payload.password,
                payload.role,
                is_first_admin=is_first_admin
            )
            logger.info(
                "User created successfully: user_id=%s role=%s email=%s",
                user.id,
                payload.role,
                user.email,
            )

        except ConflictError:
            raise
        except IntegrityError as e:
            logger.error(f"Database integrity error during registration: {str(e)}", exc_info=True)
            session.rollback()
            raise ConflictError("Email already registered")
        except SQLAlchemyError as e:
            logger.error(f"Database error during registration: {str(e)}", exc_info=True)
            session.rollback()
            raise DatabaseError("Registration failed - database error", original_error=e)

        verification_token = None
        if payload.role in (Role.admin, Role.company):
            try:
                logger.info(
                    "Creating verification token for user_id=%s email=%s",
                    user.id,
                    user.email,
                )
                verification_token = create_email_verification_token(user.id)
                logger.info(
                    "Verification token created for user_id=%s email=%s",
                    user.id,
                    user.email,
                )
                background_tasks.add_task(
                    _send_email_verification_email,
                    user.email,
                    verification_token,
                )
                logger.info(
                    "Background task added: email verification for user_id=%s email=%s",
                    user.id,
                    user.email,
                )
            except TokenError as e:
                logger.error(f"Failed to create verification token: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to send verification email")
            except Exception:
                logger.exception(
                    "Failed before queuing verification background task for user_id=%s email=%s",
                    user.id,
                    user.email,
                )
                raise HTTPException(status_code=500, detail="Failed to send verification email")
        else:
            logger.info(
                "Verification email not required for role=%s email=%s",
                payload.role,
                payload.email,
            )

        response = {
            "message": "Registration successful. Verify your email before logging in.",
            "email_verification_sent": verification_token is not None,
        }
        if EXPOSE_TOKENS_IN_RESPONSES:
            response["verification_token"] = verification_token
            logger.debug(f"Verification token exposed in DEBUG mode")

        logger.info(
            "Registration response returning for email=%s email_verification_sent=%s",
            payload.email,
            verification_token is not None,
        )
        return response

    except (ConflictError, TokenError, DatabaseError) as e:
        logger.warning(f"Registration error: {e.message}")
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Unexpected registration error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session)
):
    try:
        identifier = form_data.username
        logger.info(f"Login attempt for: {identifier}")

        if ENABLE_RATE_LIMITING:
            allowed, remaining = check_rate_limit(
                identifier,
                max_attempts=MAX_LOGIN_ATTEMPTS,
                window_seconds=LOGIN_ATTEMPT_WINDOW_SECONDS
            )
            if not allowed:
                logger.warning(f"Login rate limited for: {identifier}")
                record_auth_failure(identifier)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many login attempts. Try again later."
                )

        user_by_email = session.exec(select(User).where(User.email == identifier)).first()
        if user_by_email and not getattr(user_by_email, "is_active", True):
            logger.warning(f"Login attempt on deactivated account: {identifier}")
            record_auth_failure(identifier)
            raise AuthenticationError("Account is deactivated")

        user = crud.authenticate_user(session, identifier, form_data.password)
        if not user:
            logger.warning(f"Failed login attempt for: {identifier}")
            record_auth_failure(identifier)
            if ENABLE_RATE_LIMITING:
                record_attempt(identifier, count=1)
            raise AuthenticationError("Incorrect credentials")

        if user.role in (Role.admin, Role.company) and not getattr(user, "email_verified", False):
            logger.warning(f"Login blocked - email not verified: {identifier}")
            record_auth_failure(identifier)
            raise AuthenticationError("Email not verified. Please verify your email first.")

        if user.role == Role.admin:
            if not user.is_first_admin and not user.verified:
                logger.warning(f"Login blocked - admin not verified: {identifier}")
                record_auth_failure(identifier)
                raise AuthenticationError("Admin not verified. Please wait for approval.")

        try:
            token = create_access_token({"sub": str(user.id), "role": user.role})
            
            if ENABLE_RATE_LIMITING:
                reset_limit(identifier)

            logger.info(f"Successful login for user: {user.id}")
            return {"access_token": token}

        except TokenError as e:
            logger.error(f"Token creation failed for user {user.id}: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to create session")

    except AuthenticationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected login error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/verify-email")
def verify_email(
    payload: EmailVerificationConfirmIn,
    session: Session = Depends(get_session)
):
    try:
        logger.debug("Email verification attempt")
        
        user_id = verify_email_verification_token(payload.token, session=session)
        if user_id is None:
            logger.warning("Email verification failed - invalid, expired, or already used token")
            raise TokenError("Invalid or expired verification token")

        user = crud.mark_user_email_verified(session, user_id)
        if not user:
            logger.warning(f"Email verification failed - user not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found or inactive")

        mark_token_as_used(session, payload.token, user_id, "email_verification")

        new_token = create_access_token({"sub": str(user.id), "role": user.role})
        
        logger.info(f"Email verified successfully for user: {user_id}")
        return {
            "message": "Email verified successfully",
            "access_token": new_token,
            "token_type": "bearer"
        }

    except TokenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Email verification failed")


@router.post("/resend-verification")
def resend_verification_email(
    payload: EmailVerificationRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    try:
        identifier = f"resend_verification:{payload.email}"
        
        if ENABLE_RATE_LIMITING:
            allowed, remaining = check_rate_limit(
                identifier,
                max_attempts=MAX_EMAIL_VERIFICATION_RESEND,
                window_seconds=EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS
            )
            if not allowed:
                logger.warning(f"Email verification resend rate limited for: {payload.email}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many verification resend attempts. Try again later."
                )
        
        logger.debug(f"Resend verification attempt for: {payload.email}")
        
        user = crud.get_user_by_email(session, payload.email)
        verification_token = None

        if user and user.role in (Role.admin, Role.company) and not getattr(user, "email_verified", False):
            try:
                verification_token = create_email_verification_token(user.id)
                background_tasks.add_task(
                    _send_email_verification_email,
                    user.email,
                    verification_token
                )
                logger.info(f"Verification email resent for: {payload.email}")
                if ENABLE_RATE_LIMITING:
                    record_attempt(identifier, count=1)
            except TokenError as e:
                logger.error(f"Failed to create verification token: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to send verification email")

        response = {
            "message": "If the account exists and still needs verification, verification instructions have been queued.",
        }
        if EXPOSE_TOKENS_IN_RESPONSES:
            response["verification_token"] = verification_token
            logger.debug("Verification token exposed in DEBUG mode")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resend verification error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Resend verification failed")


@router.post("/forgot-password")
def forgot_password(
    payload: PasswordResetRequestIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    start_time = time.time()
    try:
        logger.debug(f"Password reset request for: {payload.email}")
        
        user = crud.get_user_by_email(session, payload.email)
        reset_token = None

        if user:
            try:
                reset_token = create_password_reset_token(user.id)
                background_tasks.add_task(
                    _send_password_reset_email,
                    user.email,
                    reset_token
                )
                logger.info(f"Password reset email queued for: {payload.email}")
            except TokenError as e:
                logger.error(f"Failed to create password reset token: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to send reset email")

        response = {
            "message": "If the account exists, reset instructions have been queued.",
        }
        if EXPOSE_TOKENS_IN_RESPONSES:
            response["reset_token"] = reset_token
            logger.debug("Reset token exposed in DEBUG mode")

        elapsed = time.time() - start_time
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Forgot password error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Password reset request failed")


@router.post("/reset-password")
def reset_password(
    payload: PasswordResetConfirmIn,
    session: Session = Depends(get_session)
):
    try:
        identifier = "password_reset"
        
        if ENABLE_RATE_LIMITING:
            allowed, remaining = check_rate_limit(
                identifier,
                max_attempts=MAX_PASSWORD_RESET_ATTEMPTS,
                window_seconds=PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS
            )
            if not allowed:
                logger.warning(f"Password reset rate limited")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many password reset attempts. Try again later."
                )
        
        logger.debug("Password reset attempt")
        
        user_id = verify_password_reset_token(payload.token, session=session)
        if user_id is None:
            logger.warning("Password reset failed - invalid, expired, or already used token")
            if ENABLE_RATE_LIMITING:
                record_attempt(identifier, count=1)
            raise TokenError("Invalid or expired reset token")

        user = crud.update_user_password(session, user_id, payload.new_password)
        if not user:
            logger.warning(f"Password reset failed - user not found: {user_id}")
            if ENABLE_RATE_LIMITING:
                record_attempt(identifier, count=1)
            raise HTTPException(status_code=404, detail="User not found or inactive")

        mark_token_as_used(session, payload.token, user_id, "password_reset")

        if ENABLE_RATE_LIMITING:
            reset_limit(identifier)

        logger.info(f"Password reset successful for user: {user_id}")
        return {"message": "Password reset successful"}

    except TokenError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Password reset failed")


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    try:
        logger.debug(f"Password change attempt for user: {current_user.id}")
        
        user = session.get(User, current_user.id)
        if not user or not getattr(user, "is_active", True):
            logger.warning(f"Password change failed - user not found or deactivated: {current_user.id}")
            raise HTTPException(status_code=404, detail="User not found or inactive")

        if not verify_password(payload.old_password, user.password_hash):
            logger.warning(f"Password change failed - invalid old password for user: {current_user.id}")
            raise HTTPException(status_code=401, detail="Incorrect old password")

        user = crud.update_user_password(session, current_user.id, payload.new_password)
        if not user:
            logger.warning(f"Password change failed - could not update: {current_user.id}")
            raise HTTPException(status_code=500, detail="Failed to update password")

        logger.info(f"Password changed successfully for user: {current_user.id}")
        return {"message": "Password changed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Password change failed")
