from __future__ import annotations

import re
from uuid import UUID

from pydantic import EmailStr, HttpUrl, validator


def validate_uuid(value: str) -> str:
    try:
        UUID(value)
        return value
    except ValueError as exc:
        raise ValueError("Invalid UUID format") from exc


def validate_phone(value: str) -> str:
    cleaned = re.sub(r"[^0-9+]", "", value)
    if len(cleaned) < 7 or len(cleaned) > 15:
        raise ValueError("Invalid phone number")
    return cleaned
