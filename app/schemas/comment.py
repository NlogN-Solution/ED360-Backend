from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, constr

from ..models.enums import CommentEntityType


class CommentCreate(BaseModel):
    entity_type: CommentEntityType
    entity_id: UUID
    body: constr(strip_whitespace=True, min_length=1, max_length=4000)


class CommentRead(BaseModel):
    id: UUID
    entity_type: CommentEntityType
    entity_id: UUID
    author_id: UUID
    body: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CommentList(BaseModel):
    items: list[CommentRead]
    total: int


class CommentCounts(BaseModel):
    # Keyed by entity id (as a string — JSON object keys can't be UUIDs).
    counts: dict[str, int]
