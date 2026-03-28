"""
Simple in-process security alert counters.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Deque, Dict

from .config import (
    ALERT_500_THRESHOLD,
    ALERT_500_WINDOW_SECONDS,
    ALERT_AUTH_FAILURE_THRESHOLD,
    ALERT_AUTH_FAILURE_WINDOW_SECONDS,
)
from .datetime_utils import utc_now
from .logger import get_logger

logger = get_logger(__name__)

_server_error_events: Deque[datetime] = deque()
_auth_failure_events: Dict[str, Deque[datetime]] = {}


def _prune(events: Deque[datetime], window_seconds: int) -> None:
    cutoff = utc_now() - timedelta(seconds=window_seconds)
    while events and events[0] < cutoff:
        events.popleft()


def record_server_error(path: str) -> None:
    now = utc_now()
    _server_error_events.append(now)
    _prune(_server_error_events, ALERT_500_WINDOW_SECONDS)
    if len(_server_error_events) >= ALERT_500_THRESHOLD:
        logger.warning(
            "SECURITY_ALERT repeated_500_errors count=%s window_seconds=%s sample_path=%s",
            len(_server_error_events),
            ALERT_500_WINDOW_SECONDS,
            path,
        )


def record_auth_failure(identifier: str) -> None:
    key = (identifier or "unknown").strip().lower() or "unknown"
    events = _auth_failure_events.setdefault(key, deque())
    events.append(utc_now())
    _prune(events, ALERT_AUTH_FAILURE_WINDOW_SECONDS)
    if len(events) >= ALERT_AUTH_FAILURE_THRESHOLD:
        logger.warning(
            "SECURITY_ALERT repeated_auth_failures identifier=%s count=%s window_seconds=%s",
            key,
            len(events),
            ALERT_AUTH_FAILURE_WINDOW_SECONDS,
        )

