from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseEnvelope(BaseModel, Generic[T]):
    success: bool = Field(default=True)
    message: str | None = None
    data: T | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = Field(default=True)
    data: list[T]
    pagination: dict[str, int]
