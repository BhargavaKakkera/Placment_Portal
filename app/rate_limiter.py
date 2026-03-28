"""
Basic rate limiting for authentication attempts.

Implements in-memory rate limiting for login and password reset attempts.
Resets after application restart or configurable time window.
"""

import logging
import time
import threading
from collections import defaultdict
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# Store: {key: [(timestamp, attempt_count)]}
_rate_limit_store: Dict[str, list] = defaultdict(list)
_rate_limit_lock = threading.Lock()


def _normalize_key(key: str) -> str:
    """Normalize identifier keys to avoid bypass via casing/spacing."""
    return (key or "").strip().lower()


def check_rate_limit(
    key: str, max_attempts: int = 5, window_seconds: int = 900
) -> Tuple[bool, int]:
    """
    Check if rate limit exceeded for a given key (e.g., email or IP).

    Args:
        key: Unique identifier (email, IP, etc.)
        max_attempts: Maximum attempts allowed
        window_seconds: Time window in seconds (default: 15 minutes)

    Returns:
        Tuple of (allowed: bool, remaining_attempts: int)
    """
    key = _normalize_key(key)
    current_time = time.time()

    with _rate_limit_lock:
        # Clean old entries outside window
        _rate_limit_store[key] = [
            (timestamp, count) for timestamp, count in _rate_limit_store[key]
            if current_time - timestamp < window_seconds
        ]

        # Count attempts in window
        attempt_count = sum(count for _, count in _rate_limit_store[key])

        if attempt_count >= max_attempts:
            logger.warning(f"Rate limit exceeded for key: {key} (attempts: {attempt_count})")
            return False, 0

        return True, max_attempts - attempt_count - 1


def record_attempt(key: str, count: int = 1) -> None:
    """
    Record an attempt for rate limiting.

    Args:
        key: Unique identifier
        count: Number of attempts to record (default: 1)
    """
    key = _normalize_key(key)
    current_time = time.time()
    with _rate_limit_lock:
        _rate_limit_store[key].append((current_time, count))
    logger.debug(f"Rate limit attempt recorded for key: {key}")


def reset_limit(key: str) -> None:
    """
    Reset rate limit for a given key (e.g., after successful login).

    Args:
        key: Unique identifier
    """
    key = _normalize_key(key)
    with _rate_limit_lock:
        if key in _rate_limit_store:
            del _rate_limit_store[key]
            logger.debug(f"Rate limit reset for key: {key}")


def get_remaining_time(key: str, window_seconds: int = 900) -> int:
    """
    Get remaining time (in seconds) before rate limit resets.

    Args:
        key: Unique identifier
        window_seconds: Time window in seconds

    Returns:
        Seconds remaining before limit resets
    """
    key = _normalize_key(key)
    with _rate_limit_lock:
        if key not in _rate_limit_store or not _rate_limit_store[key]:
            return 0

        oldest_attempt = min(timestamp for timestamp, _ in _rate_limit_store[key])
        elapsed = time.time() - oldest_attempt
        remaining = max(0, window_seconds - int(elapsed))
        return remaining
