"""Shared datetime helpers for consistent UTC handling."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time as a naive datetime for DB storage/comparison."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc_now_aware() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


def to_utc_naive(dt: datetime) -> datetime:
    """Normalize datetime values to UTC-naive for consistent DB comparisons."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)
