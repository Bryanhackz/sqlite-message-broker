# © 2026 Bryan Gil — github.com/Bryanhackz — br4yangil006@gmail.com
"""Centralized input validation with allowlists and bounds."""

from __future__ import annotations

import re

QUEUE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
LABEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
MAX_BODY_BYTES = 64 * 1024
MAX_QUEUE_NAME = 64


class ValidationError(ValueError):
    """Raised when user input fails validation."""


def validate_queue_name(value: object) -> str:
    """Validate a queue name against the allowlist regex and max length."""
    if not isinstance(value, str):
        raise ValidationError("queue name must be a string")
    if len(value) > MAX_QUEUE_NAME:
        raise ValidationError("queue name too long")
    if not QUEUE_NAME_RE.match(value):
        raise ValidationError("queue name must match [a-z0-9][a-z0-9_-]{0,63}")
    return value


def validate_label(value: object) -> str:
    """Validate an API-key label."""
    if not isinstance(value, str) or not LABEL_RE.match(value):
        raise ValidationError("label must match [A-Za-z0-9._-]{1,64}")
    return value


def validate_body(value: object) -> str:
    """Validate a message body (JSON string) and its UTF-8 size."""
    if not isinstance(value, str):
        raise ValidationError("body must be a string")
    if len(value.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValidationError("body exceeds 64KiB")
    return value


def validate_role(value: object) -> str:
    """Validate an API-key role against the closed allowlist."""
    if value not in ("producer", "consumer", "admin"):
        raise ValidationError("role must be producer|consumer|admin")
    return value  # type: ignore[return-value]