"""
Authentication and token management.

Handles JWT token creation/verification, password hashing, email/password reset tokens,
and role-based access control with logging and exception handling.
"""

from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlmodel import Session

from .config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
    EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES,
    JWT_SECRET_KEY,
)
from .models import User
from .database import get_session
from .datetime_utils import utc_now_aware
from .exceptions import AuthenticationError, AuthorizationError, TokenError
from .logger import get_logger

logger = get_logger(__name__)
PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    """
    Hash password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    try:
        hashed = PWD_CONTEXT.hash(password)
        logger.debug("Password hashed successfully")
        return hashed
    except Exception as e:
        logger.error(f"Password hashing failed: {str(e)}", exc_info=True)
        raise


def verify_password(plain: str, hashed: str) -> bool:
    """
    Verify plain password against hashed password.

    Args:
        plain: Plain text password
        hashed: Hashed password

    Returns:
        True if passwords match, False otherwise
    """
    try:
        result = PWD_CONTEXT.verify(plain, hashed)
        if not result:
            logger.debug("Password verification failed - passwords do not match")
        return result
    except Exception as e:
        logger.error(f"Password verification error: {str(e)}", exc_info=True)
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT access token.

    Args:
        data: Token payload data
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT token

    Raises:
        TokenError: If token creation fails
    """
    try:
        to_encode = data.copy()
        expire = utc_now_aware() + (
            expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        subject = to_encode.pop("user_id", None)
        if subject is not None and "sub" not in to_encode:
            to_encode["sub"] = str(subject)
        to_encode.update({"exp": expire})
        token = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
        logger.debug("Access token created successfully")
        return token
    except Exception as e:
        logger.error(f"Access token creation failed: {str(e)}", exc_info=True)
        raise TokenError("Failed to create access token", original_error=e)


def verify_access_token(token: str) -> Optional[int]:
    """
    Verify and decode JWT access token.

    Args:
        token: JWT token to verify

    Returns:
        User ID if valid, None otherwise
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            logger.warning("Access token missing 'sub' claim")
            return None
        logger.debug(f"Access token verified for user_id: {user_id_raw}")
        return int(user_id_raw)
    except JWTError as e:
        logger.warning(f"Access token verification failed: {str(e)}")
        return None
    except (TypeError, ValueError) as e:
        logger.error(f"Access token parsing error: {str(e)}", exc_info=True)
        return None


def create_password_reset_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT token for password reset.

    Args:
        user_id: User ID
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT token

    Raises:
        TokenError: If token creation fails
    """
    try:
        expire = utc_now_aware() + (
            expires_delta or timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        )
        payload = {
            "sub": str(user_id),
            "purpose": "password_reset",
            "exp": expire,
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
        logger.debug(f"Password reset token created for user_id: {user_id}")
        return token
    except Exception as e:
        logger.error(f"Password reset token creation failed: {str(e)}", exc_info=True)
        raise TokenError("Failed to create password reset token", original_error=e)


def create_email_verification_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create JWT token for email verification.

    Args:
        user_id: User ID
        expires_delta: Custom expiration time

    Returns:
        Encoded JWT token

    Raises:
        TokenError: If token creation fails
    """
    try:
        expire = utc_now_aware() + (
            expires_delta or timedelta(minutes=EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES)
        )
        payload = {
            "sub": str(user_id),
            "purpose": "email_verification",
            "exp": expire,
        }
        token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
        logger.debug(f"Email verification token created for user_id: {user_id}")
        return token
    except Exception as e:
        logger.error(f"Email verification token creation failed: {str(e)}", exc_info=True)
        raise TokenError("Failed to create email verification token", original_error=e)


def verify_password_reset_token(token: str) -> Optional[int]:
    """
    Verify JWT token is for password reset.

    Args:
        token: JWT token to verify

    Returns:
        User ID if valid and token purpose is password_reset, None otherwise
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "password_reset":
            logger.warning("Token purpose is not password_reset")
            return None
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            logger.warning("Password reset token missing 'sub' claim")
            return None
        logger.debug(f"Password reset token verified for user_id: {user_id_raw}")
        return int(user_id_raw)
    except JWTError as e:
        logger.warning(f"Password reset token verification failed: {str(e)}")
        return None
    except (TypeError, ValueError) as e:
        logger.error(f"Password reset token parsing error: {str(e)}", exc_info=True)
        return None


def verify_email_verification_token(token: str) -> Optional[int]:
    """
    Verify JWT token is for email verification.

    Args:
        token: JWT token to verify

    Returns:
        User ID if valid and token purpose is email_verification, None otherwise
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "email_verification":
            logger.warning("Token purpose is not email_verification")
            return None
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            logger.warning("Email verification token missing 'sub' claim")
            return None
        logger.debug(f"Email verification token verified for user_id: {user_id_raw}")
        return int(user_id_raw)
    except JWTError as e:
        logger.warning(f"Email verification token verification failed: {str(e)}")
        return None
    except (TypeError, ValueError) as e:
        logger.error(f"Email verification token parsing error: {str(e)}", exc_info=True)
        return None


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    """
    Get and validate current authenticated user.

    Args:
        token: JWT access token
        session: Database session

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    try:
        user_id = verify_access_token(token)
        if user_id is None:
            logger.warning("Invalid access token provided")
            raise AuthenticationError("Invalid token")

        user = session.get(User, user_id)
        if not user:
            logger.warning(f"User not found for user_id: {user_id}")
            raise AuthenticationError("User not found")

        if not getattr(user, "is_active", True):
            logger.warning(f"Access attempt from inactive user: {user_id}")
            raise AuthorizationError("User account is deactivated")

        logger.debug(f"User {user_id} authenticated successfully")
        return user
    except (AuthenticationError, AuthorizationError) as e:
        raise HTTPException(
            status_code=e.status_code,
            detail=e.message,
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_role(required_role: str):
    """
    Dependency that ensures current user has required role.

    Args:
        required_role: Required user role

    Returns:
        Dependency function that checks role
    """
    def _role_check(user: User = Depends(get_current_user)) -> User:
        """Check if user has required role."""
        if user.role != required_role:
            logger.warning(f"Authorization failed: user {user.id} role {user.role} != {required_role}")
            raise AuthorizationError("Insufficient permissions")
        logger.debug(f"Authorization passed for user {user.id}")
        return user

    return _role_check


def get_current_student(user: User = Depends(get_current_user)) -> User:
    """
    Get current student user.

    Args:
        user: Current authenticated user

    Returns:
        Current student user

    Raises:
        HTTPException: If user is not a student
    """
    if user.role != Role.student:
        logger.warning(f"Student access denied for non-student user: {user.id}")
        raise AuthorizationError("Only students allowed")
    return user


def get_current_company(user: User = Depends(get_current_user)) -> User:
    """
    Get current company user with email verification check.

    Args:
        user: Current authenticated user

    Returns:
        Current company user

    Raises:
        HTTPException: If user is not a company or email not verified
    """
    if user.role != Role.company:
        logger.warning(f"Company access denied for non-company user: {user.id}")
        raise AuthorizationError("Only companies allowed")

    if not getattr(user, "email_verified", False):
        logger.info(f"Company access denied - email not verified: {user.id}")
        raise AuthorizationError("Company email not verified. Please verify your email first.")

    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """
    Get current admin user.

    Args:
        user: Current authenticated user

    Returns:
        Current admin user

    Raises:
        HTTPException: If user is not an admin
    """
    if user.role != Role.admin:
        logger.warning(f"Admin access denied for non-admin user: {user.id}")
        raise AuthorizationError("Only admins allowed")
    return user


def get_verified_admin(user: User = Depends(get_current_admin)):
    """
    Check if user has admin role AND is verified.
    - First admin (is_first_admin=True) is automatically verified
    - Other admins need to be verified by first admin
    """
    if user.role != Role.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins allowed")
    
    if not getattr(user, "email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin email not verified. Please verify your email first."
        )

    # First admin is always admin-approved after email verification.
    if user.is_first_admin:
        return user
    
    # Other admins need verification
    if not user.verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin not verified. Please wait for approval from first admin."
        )
    
    return user
