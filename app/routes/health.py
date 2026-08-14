from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", summary="Health check", description="Check service health.")
async def health() -> dict[str, str]:
    return {"status": "ok"}
