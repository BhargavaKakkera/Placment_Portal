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
    SECRET_KEY,
)
from .models import User
from .database import get_session
from .datetime_utils import utc_now_aware

PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return PWD_CONTEXT.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return PWD_CONTEXT.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = utc_now_aware() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    subject = to_encode.pop("user_id", None)
    if subject is not None and "sub" not in to_encode:
        to_encode["sub"] = str(subject)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_access_token(token: str) -> Optional[int]:
    """Return the access token user id if the token is valid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            return None
        return int(user_id_raw)
    except (JWTError, TypeError, ValueError):
        return None


def create_password_reset_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT token specifically for password reset."""
    expire = utc_now_aware() + (
        expires_delta or timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(user_id),
        "purpose": "password_reset",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_email_verification_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT token specifically for email verification."""
    expire = utc_now_aware() + (
        expires_delta or timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(user_id),
        "purpose": "email_verification",
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[int]:
    """Return user_id if token is valid and meant for password reset."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "password_reset":
            return None
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            return None
        return int(user_id_raw)
    except (JWTError, TypeError, ValueError):
        return None


def verify_email_verification_token(token: str) -> Optional[int]:
    """Return user_id if token is valid and meant for email verification."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("purpose") != "email_verification":
            return None
        user_id_raw = payload.get("sub")
        if user_id_raw is None:
            return None
        return int(user_id_raw)
    except (JWTError, TypeError, ValueError):
        return None


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user_id = verify_access_token(token)
    if user_id is None:
        raise credentials_exception
    user = session.get(User, user_id)
    if not user:
        raise credentials_exception
    if not getattr(user, "is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    return user


def require_role(required_role: str):
    # Returns a dependency that ensures the current user has the required role.
    def _role_check(user: User = Depends(get_current_user)):
        if user.role != required_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user

    return _role_check


def get_current_student(user: User = Depends(get_current_user)):
    if user.role != "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only students allowed")
    return user


def get_current_company(user: User = Depends(get_current_user)):
    if user.role != "company":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only companies allowed")
    if not getattr(user, "email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Company email not verified. Please verify your email first."
        )
    return user


def get_current_admin(user: User = Depends(get_current_user)):
    """Check if user has admin role"""
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins allowed")
    if not getattr(user, "email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin email not verified. Please verify your email first."
        )
    return user


def get_verified_admin(user: User = Depends(get_current_admin)):
    """
    Check if user has admin role AND is verified.
    - First admin (is_first_admin=True) is automatically verified
    - Other admins need to be verified by first admin
    """
    if user.role != "admin":
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
