from __future__ import annotations

from typing import Any

from fastapi import Query


def pagination_params(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str | None = Query(None, description="Field to sort by"),
    order: str = Query("asc", regex="^(asc|desc)$", description="Sort order"),
) -> dict[str, Any]:
    return {"page": page, "limit": limit, "sort_by": sort_by, "order": order}
