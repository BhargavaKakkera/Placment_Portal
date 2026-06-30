"""
Application configuration.

Loads environment variables and provides configuration for the application.
Validates all required configuration at startup.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Initialize logger before any validations
logger = logging.getLogger(__name__)


def _validate_secret_key(key: str, key_name: str) -> None:
    """
    Validate secret key has minimum length for cryptographic security.

    Args:
        key: Secret key to validate
        key_name: Name of the key for logging

    Raises:
        RuntimeError: If key is too short or invalid
    """
    if not key or len(key) < 32:
        raise RuntimeError(f"{key_name} must be at least 32 characters long")
    logger.debug(f"{key_name} validation passed")


def _validate_positive_int(value: int, name: str) -> None:
    """
    Validate that a value is a positive integer.

    Args:
        value: Value to validate
        name: Name of the value for logging

    Raises:
        RuntimeError: If value is not positive
    """
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    logger.debug(f"{name} validation passed")


def _getenv_stripped(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is None:
        return None
    return value.strip()


# ===== SECRET KEY CONFIGURATION =====
# Backward compatibility:
# - SECRET_KEY can act as a single base key
# - JWT_SECRET_KEY and SESSION_SECRET_KEY can override independently
SECRET_KEY = os.getenv("SECRET_KEY")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or SECRET_KEY
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY") or SECRET_KEY

if not JWT_SECRET_KEY or not SESSION_SECRET_KEY:
    raise RuntimeError(
        "Set SECRET_KEY (single-key mode) or both JWT_SECRET_KEY and SESSION_SECRET_KEY"
    )

_validate_secret_key(JWT_SECRET_KEY, "JWT_SECRET_KEY")
_validate_secret_key(SESSION_SECRET_KEY, "SESSION_SECRET_KEY")

if JWT_SECRET_KEY == SESSION_SECRET_KEY:
    logger.warning(
        "JWT and session keys are identical. Consider separate keys for stronger key isolation."
    )

# ===== DATABASE CONFIGURATION =====
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

DB_CONNECT_TIMEOUT_SECONDS = int(os.getenv("DB_CONNECT_TIMEOUT_SECONDS", "5"))
_validate_positive_int(DB_CONNECT_TIMEOUT_SECONDS, "DB_CONNECT_TIMEOUT_SECONDS")

# ===== TOKEN CONFIGURATION =====
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = int(os.getenv("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "15"))
EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES = int(os.getenv("EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES", "24"))
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))

_validate_positive_int(ACCESS_TOKEN_EXPIRE_MINUTES, "ACCESS_TOKEN_EXPIRE_MINUTES")
_validate_positive_int(PASSWORD_RESET_TOKEN_EXPIRE_MINUTES, "PASSWORD_RESET_TOKEN_EXPIRE_MINUTES")
_validate_positive_int(EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES, "EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES")
_validate_positive_int(SESSION_TIMEOUT_MINUTES, "SESSION_TIMEOUT_MINUTES")

# ===== DEBUG & ENVIRONMENT =====
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENABLE_EMAIL_VERIFICATION = os.getenv("ENABLE_EMAIL_VERIFICATION", "true").lower() == "true"
ENABLE_RATE_LIMITING = os.getenv("ENABLE_RATE_LIMITING", "true").lower() == "true"
ENABLE_EMAIL_DELIVERY = os.getenv("ENABLE_EMAIL_DELIVERY", "false").lower() == "true"
# Only expose tokens in DEBUG mode for development convenience
# In production, tokens are never exposed in responses
EXPOSE_TOKENS_IN_RESPONSES = DEBUG and os.getenv("EXPOSE_TOKENS_IN_RESPONSES", "false").lower() == "true"
APP_BASE_URL = _getenv_stripped("APP_BASE_URL", "http://localhost:8000").rstrip("/")

# ===== EMAIL DELIVERY CONFIGURATION =====
SMTP_HOST = _getenv_stripped("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = _getenv_stripped("SMTP_USERNAME")
SMTP_PASSWORD = _getenv_stripped("SMTP_PASSWORD")
SMTP_FROM_EMAIL = _getenv_stripped("SMTP_FROM_EMAIL")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "false").lower() == "true"
EMAIL_TEST_TOKEN = _getenv_stripped("EMAIL_TEST_TOKEN")

if ENABLE_EMAIL_DELIVERY:
    if not SMTP_HOST or not SMTP_FROM_EMAIL:
        raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL must be set when ENABLE_EMAIL_DELIVERY=true")
    _validate_positive_int(SMTP_PORT, "SMTP_PORT")


def email_runtime_config_summary() -> dict:
    """
    Return non-secret email configuration values as loaded by this process.
    """
    return {
        "ENABLE_EMAIL_DELIVERY": ENABLE_EMAIL_DELIVERY,
        "SMTP_HOST": SMTP_HOST,
        "SMTP_PORT": SMTP_PORT,
        "SMTP_USERNAME_present": bool(SMTP_USERNAME),
        "SMTP_PASSWORD_present": bool(SMTP_PASSWORD),
        "SMTP_FROM_EMAIL": SMTP_FROM_EMAIL,
        "SMTP_USE_TLS": SMTP_USE_TLS,
        "SMTP_USE_SSL": SMTP_USE_SSL,
        "APP_BASE_URL": APP_BASE_URL,
        "EMAIL_TEST_TOKEN_present": bool(EMAIL_TEST_TOKEN),
        "raw_env_present": {
            "ENABLE_EMAIL_DELIVERY": "ENABLE_EMAIL_DELIVERY" in os.environ,
            "SMTP_HOST": "SMTP_HOST" in os.environ,
            "SMTP_PORT": "SMTP_PORT" in os.environ,
            "SMTP_USERNAME": "SMTP_USERNAME" in os.environ,
            "SMTP_PASSWORD": "SMTP_PASSWORD" in os.environ,
            "SMTP_FROM_EMAIL": "SMTP_FROM_EMAIL" in os.environ,
            "SMTP_USE_TLS": "SMTP_USE_TLS" in os.environ,
            "SMTP_USE_SSL": "SMTP_USE_SSL" in os.environ,
            "APP_BASE_URL": "APP_BASE_URL" in os.environ,
            "EMAIL_TEST_TOKEN": "EMAIL_TEST_TOKEN" in os.environ,
        },
    }

# ===== RATE LIMITING CONFIGURATION =====
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_ATTEMPT_WINDOW_SECONDS = int(os.getenv("LOGIN_ATTEMPT_WINDOW_SECONDS", "900"))
MAX_PASSWORD_RESET_ATTEMPTS = int(os.getenv("MAX_PASSWORD_RESET_ATTEMPTS", "5"))
PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS = int(os.getenv("PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS", "900"))
MAX_EMAIL_VERIFICATION_RESEND = int(os.getenv("MAX_EMAIL_VERIFICATION_RESEND", "3"))
EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS = int(os.getenv("EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS", "3600"))
ALERT_500_THRESHOLD = int(os.getenv("ALERT_500_THRESHOLD", "5"))
ALERT_500_WINDOW_SECONDS = int(os.getenv("ALERT_500_WINDOW_SECONDS", "300"))
ALERT_AUTH_FAILURE_THRESHOLD = int(os.getenv("ALERT_AUTH_FAILURE_THRESHOLD", "10"))
ALERT_AUTH_FAILURE_WINDOW_SECONDS = int(os.getenv("ALERT_AUTH_FAILURE_WINDOW_SECONDS", "300"))

_validate_positive_int(MAX_LOGIN_ATTEMPTS, "MAX_LOGIN_ATTEMPTS")
_validate_positive_int(LOGIN_ATTEMPT_WINDOW_SECONDS, "LOGIN_ATTEMPT_WINDOW_SECONDS")
_validate_positive_int(MAX_PASSWORD_RESET_ATTEMPTS, "MAX_PASSWORD_RESET_ATTEMPTS")
_validate_positive_int(PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS, "PASSWORD_RESET_ATTEMPT_WINDOW_SECONDS")
_validate_positive_int(MAX_EMAIL_VERIFICATION_RESEND, "MAX_EMAIL_VERIFICATION_RESEND")
_validate_positive_int(EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS, "EMAIL_VERIFICATION_RESEND_WINDOW_SECONDS")
_validate_positive_int(ALERT_500_THRESHOLD, "ALERT_500_THRESHOLD")
_validate_positive_int(ALERT_500_WINDOW_SECONDS, "ALERT_500_WINDOW_SECONDS")
_validate_positive_int(ALERT_AUTH_FAILURE_THRESHOLD, "ALERT_AUTH_FAILURE_THRESHOLD")
_validate_positive_int(ALERT_AUTH_FAILURE_WINDOW_SECONDS, "ALERT_AUTH_FAILURE_WINDOW_SECONDS")

# ===== SECURITY CONFIGURATION =====
# Cookie settings for secure session management
COOKIE_SECURE = not DEBUG  # HTTPS only in production
COOKIE_HTTPONLY = True  # JavaScript cannot access cookies
COOKIE_SAMESITE = "lax"  # CSRF protection

# Password validation rules
PASSWORD_MIN_LENGTH = 8
PASSWORD_REQUIRE_DIGIT = True
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True

logger.info("Configuration validated successfully")
if DEBUG:
    logger.warning("DEBUG mode is enabled - do not use in production")
