from __future__ import annotations

from fastapi.responses import JSONResponse


def json_response(data: dict[str, object], status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status_code)
