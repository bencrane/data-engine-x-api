"""
Bright Data ingestion API wrappers.

Thin FastAPI endpoints that forward payloads to Modal ingestion functions.
"""

import os
import httpx

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/ingest/brightdata", tags=["brightdata-ingest"])

INGEST_API_KEY = os.getenv("INGEST_API_KEY")
MODAL_BASE_URL = "https://bencrane--hq-master-data-ingest"


class BrightDataIngestRequest(BaseModel):
    records: list[dict]
    metadata: dict | None = None


def _require_ingest_key(x_api_key: str | None) -> None:
    if not INGEST_API_KEY:
        raise HTTPException(status_code=500, detail="INGEST_API_KEY is not configured")
    if x_api_key != INGEST_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/indeed")
async def ingest_brightdata_indeed(
    request: BrightDataIngestRequest,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    _require_ingest_key(x_api_key)

    modal_url = f"{MODAL_BASE_URL}-ingest-brightdata-indeed-jobs.modal.run"
    payload = {"records": request.records, "metadata": request.metadata}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(modal_url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Modal function error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Modal function: {str(e)}",
        )


@router.post("/linkedin")
async def ingest_brightdata_linkedin(
    request: BrightDataIngestRequest,
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
):
    _require_ingest_key(x_api_key)

    modal_url = f"{MODAL_BASE_URL}-ingest-brightdata-linkedin-jobs.modal.run"
    payload = {"records": request.records, "metadata": request.metadata}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(modal_url, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Modal function error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to reach Modal function: {str(e)}",
        )
