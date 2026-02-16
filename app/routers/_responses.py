# app/routers/_responses.py — shared API response envelopes

from typing import Any

from fastapi.responses import JSONResponse
from pydantic import BaseModel


class DataEnvelope(BaseModel):
    data: Any


class ErrorEnvelope(BaseModel):
    error: str


def error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": message})
