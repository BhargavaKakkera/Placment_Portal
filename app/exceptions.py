import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ApplicationException(Exception):

    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL_ERROR"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(self.message)
        logger.error(f"[{error_code}] {message}", extra={"status_code": status_code})


class DatabaseError(ApplicationException):

    def __init__(self, message: str = "Database operation failed", original_error: Optional[Exception] = None):
        super().__init__(message, status_code=500, error_code="DATABASE_ERROR")
        if original_error:
            logger.error(f"Database error cause: {str(original_error)}", exc_info=True)


class AuthenticationError(ApplicationException):

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401, error_code="AUTHENTICATION_ERROR")


class AuthorizationError(ApplicationException):

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, status_code=403, error_code="AUTHORIZATION_ERROR")


class ValidationError(ApplicationException):

    def __init__(self, message: str = "Invalid input", field: Optional[str] = None):
        super().__init__(message, status_code=422, error_code="VALIDATION_ERROR")
        if field:
            logger.debug(f"Validation failed for field: {field}")


class ConflictError(ApplicationException):

    def __init__(self, message: str = "Resource conflict"):
        super().__init__(message, status_code=409, error_code="CONFLICT_ERROR")


class NotFoundError(ApplicationException):

    def __init__(self, message: str = "Resource not found", resource_id: Optional[str] = None):
        super().__init__(message, status_code=404, error_code="NOT_FOUND_ERROR")
        if resource_id:
            logger.debug(f"Resource not found: {resource_id}")


class RateLimitError(ApplicationException):

    def __init__(self, message: str = "Too many requests"):
        super().__init__(message, status_code=429, error_code="RATE_LIMIT_ERROR")


class EmailSendError(ApplicationException):

    def __init__(self, message: str = "Email send failed", original_error: Optional[Exception] = None):
        super().__init__(message, status_code=500, error_code="EMAIL_SEND_ERROR")
        if original_error:
            logger.error(f"Email send error cause: {str(original_error)}", exc_info=True)


class TokenError(ApplicationException):

    def __init__(self, message: str = "Token error"):
        super().__init__(message, status_code=401, error_code="TOKEN_ERROR")


class ConfigurationError(ApplicationException):

    def __init__(self, message: str = "Configuration error"):
        super().__init__(message, status_code=500, error_code="CONFIG_ERROR")
        logger.critical(f"Configuration error: {message}")


class InvalidURLError(ValidationError):

    def __init__(self, url: str):
        super().__init__(f"Invalid URL format", field="url")
        logger.warning(f"Invalid URL provided: {url}")
