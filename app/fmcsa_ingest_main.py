# app/fmcsa_ingest_main.py — Minimal FastAPI entrypoint for FMCSA bulk write ingestion
#
# This is a standalone service that handles only FMCSA upsert-batch and
# artifact-ingest endpoints. It shares the same database and persistence
# layer as the main data-engine-x API but deploys independently so that
# main-API deploys do not kill in-flight FMCSA chunk POST requests.

from fastapi import FastAPI

from app.middleware.gzip_request import GzipRequestMiddleware
from app.routers import fmcsa_ingest

app = FastAPI(
    title="data-engine-x-fmcsa-ingest",
    description="FMCSA bulk write ingestion service",
    version="0.1.0",
)

app.add_middleware(GzipRequestMiddleware)

app.include_router(fmcsa_ingest.router, prefix="/api/internal", tags=["fmcsa-ingest"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fmcsa-ingest"}
