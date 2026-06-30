"""
Main FastAPI application.

Initializes the FastAPI app with middleware, security headers, and startup tasks.
"""

import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from .database import run_migrations, engine
from . import crud
from .config import SESSION_SECRET_KEY, DEBUG, LOG_LEVEL, EMAIL_TEST_TOKEN, email_runtime_config_summary
from .email_service import _send_email
from .exceptions import ApplicationException
from .logger import configure_logging, get_logger, configure_uvicorn_logging
from .security_alerts import record_server_error

# Configure logging before anything else
configure_logging(log_level=LOG_LEVEL)
configure_uvicorn_logging()  # Enable uvicorn access logs
logger = get_logger(__name__)

app = FastAPI(
    title="Placement Portal - Placement Cell API",
    description="API for managing placements, students, companies, and job applications",
    version="1.0.0",
    docs_url="/docs",  # Always enable Swagger UI
    redoc_url="/redoc",  # Always enable ReDoc
    openapi_url="/openapi.json",  # Always expose OpenAPI schema
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )
        
        # HSTS header in production
        if not DEBUG:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        logger.debug(f"Security headers added for {request.method} {request.url.path}")
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add unique request ID to all requests for tracking."""
    
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = str(uuid4())[:8]
        start_time = time.perf_counter()
        logger.info(
            "Request started request_id=%s method=%s path=%s client=%s",
            request.state.request_id,
            request.method,
            request.url.path,
            request.client.host if request.client else None,
        )
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "Request failed request_id=%s method=%s path=%s duration_ms=%.2f",
                request.state.request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise
        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "Request completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request.state.request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)

# Add CORS middleware for API endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8000",
        "http://localhost",
        os.getenv("FRONTEND_URL", "http://localhost:3000")
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Add session middleware with secure cookies
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    same_site="lax",
    https_only=not DEBUG,  # HTTPS only in production
    max_age=60 * 30,  # 30 minutes session timeout
)

# Mount static files
static_path = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
logger.info(f"Static files mounted from: {static_path}")


@app.on_event("startup")
def on_startup() -> None:
    """
    Startup event: Run migrations and cleanup tasks.

    Raises:
        RuntimeError: If startup tasks fail
    """
    try:
        logger.info("Application startup beginning...")
        logger.info("Email runtime configuration at startup: %s", email_runtime_config_summary())
        
        # Run database migrations
        run_migrations()
        logger.info("Migrations completed")

        # Cleanup expired unverified users
        try:
            with Session(engine) as session:
                crud.purge_expired_unverified_users(session, older_than_days=15)
                logger.info("Cleanup of expired unverified users completed")
        except Exception as e:
            logger.error(f"Error during user cleanup: {str(e)}", exc_info=True)
            # Don't fail startup, just log the error

        # Cleanup expired tokens from blacklist
        try:
            with Session(engine) as session:
                crud.cleanup_expired_tokens(session, older_than_days=2)
                logger.info("Cleanup of expired tokens completed")
        except Exception as e:
            logger.error(f"Error during token cleanup: {str(e)}", exc_info=True)
            # Don't fail startup, just log the error

        logger.info("Application startup completed successfully")
        if DEBUG:
            logger.warning("DEBUG mode is enabled - do not use in production")
        logger.info(f"Logging level active: {LOG_LEVEL}")
        logger.info("=" * 70)
            
    except Exception as e:
        logger.critical(f"Application startup failed: {str(e)}", exc_info=True)
        raise RuntimeError("Application startup failed") from e


# Include routers
from .routers import auth, jobs, students, companies
from .routers.admin import router as admin_router
from .ui import router as ui_router

app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(students.router)
app.include_router(companies.router)
app.include_router(admin_router)
app.include_router(ui_router,include_in_schema=False)

logger.info("All routers registered")


@app.exception_handler(ApplicationException)
async def application_exception_handler(request: Request, exc: ApplicationException):
    """Handle all custom application exceptions with standard format."""
    logger.warning(
        f"Application error at {request.method} {request.url.path}: [{exc.error_code}] {exc.message}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.message,
            "error_code": exc.error_code,
            "request_id": getattr(request.state, "request_id", None)
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Convert Pydantic validation errors to user-friendly format."""
    errors = []
    for error in exc.errors():
        field = ".".join(str(x) for x in error["loc"][1:])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"]
        })
    
    logger.info(f"Validation error at {request.method} {request.url.path}: {len(errors)} error(s)")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": "Validation failed",
            "error_code": "VALIDATION_ERROR",
            "details": {"errors": errors[:5]},  # Limit to 5 errors
            "request_id": getattr(request.state, "request_id", None)
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTPException with standard format."""
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": detail,
            "error_code": f"HTTP_{exc.status_code}",
            "request_id": getattr(request.state, "request_id", None)
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unexpected errors without exposing stack traces."""
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        f"Unhandled error at {request.method} {request.url.path}: {str(exc)}",
        exc_info=True,
        extra={"request_id": request_id}
    )
    record_server_error(request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error" if not DEBUG else str(exc),
            "error_code": "INTERNAL_ERROR",
            "request_id": request_id
        },
    )


@app.get("/")
def root():
    """Redirect root to UI."""
    logger.debug("Root endpoint accessed, redirecting to /ui/")
    return RedirectResponse(url="/ui/", status_code=307)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    logger.debug("Health check called")
    return {"status": "healthy"}


@app.get("/health/email-config")
def email_config_health_check():
    """
    Report non-secret email runtime config so deployment env can be verified.
    """
    summary = email_runtime_config_summary()
    raw_env_present = summary["raw_env_present"]
    return {
        "email_delivery_enabled": summary["ENABLE_EMAIL_DELIVERY"],
        "email_provider": summary["EMAIL_PROVIDER"],
        "email_from_present": bool(summary["EMAIL_FROM"]),
        "resend_api_key_present": summary["RESEND_API_KEY_present"],
        "smtp_host_present": bool(summary["SMTP_HOST"]),
        "smtp_port": summary["SMTP_PORT"],
        "smtp_username_present": summary["SMTP_USERNAME_present"],
        "smtp_password_present": summary["SMTP_PASSWORD_present"],
        "smtp_from_email_present": bool(summary["SMTP_FROM_EMAIL"]),
        "smtp_use_tls": summary["SMTP_USE_TLS"],
        "smtp_use_ssl": summary["SMTP_USE_SSL"],
        "app_base_url": summary["APP_BASE_URL"],
        "email_test_token_present": summary["EMAIL_TEST_TOKEN_present"],
        "raw_env_present": raw_env_present,
    }


@app.post("/health/email-send-test")
def email_send_test(request: Request, to: str):
    """
    Send a diagnostic email. Requires EMAIL_TEST_TOKEN and X-Email-Test-Token.
    """
    supplied_token = request.headers.get("X-Email-Test-Token")
    if not EMAIL_TEST_TOKEN or supplied_token != EMAIL_TEST_TOKEN:
        raise HTTPException(status_code=404, detail="Not found")

    logger.info("Diagnostic email send requested for %s", to)
    _send_email(
        to,
        "Placement Portal SMTP diagnostic",
        "This is a diagnostic email from the Placement Portal Render deployment.",
    )
    logger.info("Diagnostic email send completed for %s", to)
    return {"sent": True}


@app.get(
    "/policy/lifecycle",
    tags=["Policy"],
    summary="Lifecycle policy rules for company/job/application/offer behavior",
)
def lifecycle_policy() -> Dict[str, Any]:
    """
    Canonical policy contract for frontend/admin to enforce lifecycle behavior.
    """
    return {
        "policy_version": "2026-03-27",
        "description": "Single source of truth for active vs inactive company behavior.",
        "company_state": {
            "active": {
                "can_login": True,
                "can_create_jobs": True,
                "can_manage_applications": True,
                "jobs_publicly_visible_if_verified": True,
            },
            "inactive": {
                "can_login": False,
                "can_create_jobs": False,
                "can_manage_applications": False,
                "jobs_publicly_visible_if_verified": False,
            },
        },
        "job_rules": {
            "on_company_deactivation": {
                "close_all_company_jobs": True,
                "new_applications_blocked": True,
            },
            "student_ui_visibility": {
                "only_active_verified_company_jobs_are_listed": True,
                "closed_jobs_not_listed_for_new_applications": True,
            },
        },
        "application_rules": {
            "inactive_company_cannot_progress_application_status": True,
            "student_cannot_apply_if_company_inactive": True,
        },
        "offer_rules": {
            "offered_pending_if_company_becomes_inactive": {
                "student_can_accept_or_decline": False,
                "reason": "Offer actions are blocked once the company is inactive.",
            },
            "accepted_offer_if_company_becomes_inactive": {
                "remains_in_history": True,
                "status_changes_automatically": False,
                "ui_hint": "Show company as inactive badge/context only.",
            },
        },
        "admin_rules": {
            "can_view_inactive_companies": True,
            "can_view_closed_jobs_from_inactive_companies": True,
            "can_reactivate_company": True,
        },
    }
