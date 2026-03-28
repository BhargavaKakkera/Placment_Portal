"""
Authentication endpoints.

Handles user registration, login, email verification, and password reset with
comprehensive logging, exception handling, and rate limiting.
"""

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
    EXPOSE_TOKENS_IN_RESPONSES
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

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _send_password_reset_email(email: str, token: str) -> None:
    """
    Demo background task for password reset email.
    Replace with real provider integration later.
    
    Args:
        email: User email address
        token: Password reset token (logged without exposing token value)
    """
    try:
        send_password_reset_email(email, token)
    except EmailSendError as exc:
        logger.error("Password reset email failed for %s: %s", email, exc.message)
        raise


def _send_email_verification_email(email: str, token: str) -> None:
    """
    Demo background task for email verification.
    Replace with real provider integration later.
    
    Args:
        email: User email address
        token: Email verification token (logged without exposing token value)
    """
    try:
        send_email_verification_email(email, token)
    except EmailSendError as exc:
        logger.error("Verification email failed for %s: %s", email, exc.message)
        raise


@router.post("/register", response_model=RegisterOut)
def register(
    payload: RegisterIn,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    """
    Register new user account.

    Args:
        payload: Registration data
        background_tasks: Background task manager
        session: Database session

    Returns:
        Registration response with optional verification token (debug mode only)

    Raises:
        HTTPException: On validation or conflict errors
    """
    try:
        logger.info(f"Registration attempt for role: {payload.role}, email: {payload.email}")

        if payload.role == Role.student:
            logger.warning(f"Student self-registration blocked for: {payload.email}")
            raise ConflictError("Student self-registration is disabled. Contact admin for invite.")

        is_first_admin = False
        try:
            # Auto-clean stale unverified accounts so email can be reused.
            crud.purge_expired_unverified_users(session, older_than_days=15, email=payload.email)
            logger.debug(f"Cleaned expired unverified users for: {payload.email}")

            # Serialize admin bootstrap so concurrent registrations don't create two first admins.
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
            logger.info(f"User created successfully: {user.id}, role: {payload.role}")

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
                verification_token = create_email_verification_token(user.id)
                background_tasks.add_task(
                    _send_email_verification_email,
                    user.email,
                    verification_token,
                )
                logger.info(f"Email verification task queued for: {user.email}")
            except TokenError as e:
                logger.error(f"Failed to create verification token: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail="Failed to send verification email")

        response = {
            "message": "Registration successful. Verify your email before logging in.",
            "email_verification_sent": verification_token is not None,
        }
        if EXPOSE_TOKENS_IN_RESPONSES:
            response["verification_token"] = verification_token
            logger.debug(f"Verification token exposed")

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
    """
    Login user and return access token.

    Args:
        form_data: OAuth2 form with username/password
        session: Database session

    Returns:
        Access token

    Raises:
        HTTPException: On authentication failure or rate limit
    """
    try:
        identifier = form_data.username  # Could be email
        logger.info(f"Login attempt for: {identifier}")

        # Check rate limiting
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

        # Check deactivated accounts
        user_by_email = session.exec(select(User).where(User.email == identifier)).first()
        if user_by_email and not getattr(user_by_email, "is_active", True):
            logger.warning(f"Login attempt on deactivated account: {identifier}")
            record_auth_failure(identifier)
            raise AuthenticationError("Account is deactivated")

        # Authenticate user
        user = crud.authenticate_user(session, identifier, form_data.password)
        if not user:
            logger.warning(f"Failed login attempt for: {identifier}")
            record_auth_failure(identifier)
            if ENABLE_RATE_LIMITING:
                record_attempt(identifier, count=1)
            raise AuthenticationError("Incorrect credentials")

        # Check email verification for admin and company
        if user.role in (Role.admin, Role.company) and not getattr(user, "email_verified", False):
            logger.warning(f"Login blocked - email not verified: {identifier}")
            record_auth_failure(identifier)
            raise AuthenticationError("Email not verified. Please verify your email first.")

        # Check admin verification
        if user.role == Role.admin:
            if not user.is_first_admin and not user.verified:
                logger.warning(f"Login blocked - admin not verified: {identifier}")
                record_auth_failure(identifier)
                raise AuthenticationError("Admin not verified. Please wait for approval.")

        # Generate token
        try:
            token = create_access_token({"sub": str(user.id), "role": user.role})
            
            # Reset rate limit on successful login
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
    """
    Verify user email using verification token.

    Args:
        payload: Email verification token
        session: Database session

    Returns:
        Success message

    Raises:
        HTTPException: On invalid token or user not found
    """
    try:
        logger.debug("Email verification attempt")
        
        user_id = verify_email_verification_token(payload.token)
        if user_id is None:
            logger.warning("Email verification failed - invalid or expired token")
            raise TokenError("Invalid or expired verification token")

        user = crud.mark_user_email_verified(session, user_id)
        if not user:
            logger.warning(f"Email verification failed - user not found: {user_id}")
            raise HTTPException(status_code=404, detail="User not found or inactive")

        # Issue new token after verification (session rotation)
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
    """
    Resend email verification instructions.

    Args:
        payload: Email address
        background_tasks: Background task manager
        session: Database session

    Returns:
        Generic response message

    Raises:
        HTTPException: On errors
    """
    try:
        identifier = f"resend_verification:{payload.email}"
        
        # Rate limiting
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
            logger.debug("Verification token exposed")

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
    """
    Request password reset.

    Args:
        payload: Email address
        background_tasks: Background task manager
        session: Database session

    Returns:
        Generic response message

    Raises:
        HTTPException: On errors
    """
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
            logger.debug("Reset token exposed")

        # Constant timing to prevent email enumeration
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
    """
    Reset password using reset token.

    Args:
        payload: Reset token and new password
        session: Database session

    Returns:
        Success message

    Raises:
        HTTPException: On invalid token or user not found
    """
    try:
        identifier = "password_reset"
        
        # Rate limiting
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
        
        user_id = verify_password_reset_token(payload.token)
        if user_id is None:
            logger.warning("Password reset failed - invalid or expired token")
            if ENABLE_RATE_LIMITING:
                record_attempt(identifier, count=1)
            raise TokenError("Invalid or expired reset token")

        user = crud.update_user_password(session, user_id, payload.new_password)
        if not user:
            logger.warning(f"Password reset failed - user not found: {user_id}")
            if ENABLE_RATE_LIMITING:
                record_attempt(identifier, count=1)
            raise HTTPException(status_code=404, detail="User not found or inactive")

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
    """
    Change password for authenticated user.

    Args:
        payload: Old password and new password
        current_user: Currently authenticated user
        session: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If old password is incorrect or user not found
    """
    try:
        logger.debug(f"Password change attempt for user: {current_user.id}")
        
        user = session.get(User, current_user.id)
        if not user or not getattr(user, "is_active", True):
            logger.warning(f"Password change failed - user not found or deactivated: {current_user.id}")
            raise HTTPException(status_code=404, detail="User not found or inactive")

        # Verify old password
        if not verify_password(payload.old_password, user.password_hash):
            logger.warning(f"Password change failed - invalid old password for user: {current_user.id}")
            raise HTTPException(status_code=401, detail="Incorrect old password")

        # Update to new password
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
