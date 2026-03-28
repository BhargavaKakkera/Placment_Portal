"""
Structured audit logging helpers.
"""

from __future__ import annotations

import json
from typing import Any

from .logger import get_logger

audit_logger = get_logger("app.audit")


def log_audit(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    audit_logger.info("AUDIT %s", json.dumps(payload, default=str, sort_keys=True))

