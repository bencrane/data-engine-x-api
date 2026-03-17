# app/routers/fmcsa_ingest.py — Dedicated FMCSA bulk write ingestion router
#
# Thin HTTP layer over existing per-table upsert services.
# Mounted by app/fmcsa_ingest_main.py as a standalone FastAPI service
# to decouple FMCSA ingestion deploys from the main data-engine-x API.

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings
from app.routers._responses import DataEnvelope
from app.services.carrier_registrations import upsert_carrier_registrations
from app.services.carrier_inspections import upsert_carrier_inspections
from app.services.carrier_inspection_violations import upsert_carrier_inspection_violations
from app.services.carrier_safety_basic_measures import upsert_carrier_safety_basic_measures
from app.services.carrier_safety_basic_percentiles import upsert_carrier_safety_basic_percentiles
from app.services.commercial_vehicle_crashes import upsert_commercial_vehicle_crashes
from app.services.insurance_filing_rejections import upsert_insurance_filing_rejections
from app.services.insurance_policies import upsert_insurance_policies
from app.services.insurance_policy_filings import upsert_insurance_policy_filings
from app.services.insurance_policy_history_events import upsert_insurance_policy_history_events
from app.services.operating_authority_histories import upsert_operating_authority_histories
from app.services.operating_authority_revocations import upsert_operating_authority_revocations
from app.services.out_of_service_orders import upsert_out_of_service_orders
from app.services.process_agent_filings import upsert_process_agent_filings
from app.services.motor_carrier_census_records import upsert_motor_carrier_census_records
from app.services.vehicle_inspection_citations import upsert_vehicle_inspection_citations
from app.services.vehicle_inspection_special_studies import upsert_vehicle_inspection_special_studies
from app.services.vehicle_inspection_units import upsert_vehicle_inspection_units

router = APIRouter()
security = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Auth dependency (replicated from internal.py to avoid importing that module)
# ---------------------------------------------------------------------------

def require_internal_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    settings = get_settings()
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    if credentials.credentials != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
    return None


# ---------------------------------------------------------------------------
# Request models (replicated from internal.py to avoid importing that module)
# ---------------------------------------------------------------------------

class InternalFmcsaDailyDiffRow(BaseModel):
    row_number: int
    raw_fields: dict[str, str]


class InternalUpsertFmcsaDailyDiffBatchRequest(BaseModel):
    feed_name: str
    feed_date: str
    download_url: str
    source_file_variant: Literal["daily diff", "daily", "all_with_history", "csv_export"]
    source_observed_at: str
    source_task_id: str
    source_schedule_id: str | None = None
    source_run_metadata: dict[str, Any]
    records: list[InternalFmcsaDailyDiffRow]
    use_snapshot_replace: bool = False
    is_first_chunk: bool = False


class InternalFmcsaArtifactIngestRequest(BaseModel):
    feed_name: str
    feed_date: str
    download_url: str
    source_file_variant: Literal["daily diff", "daily", "all_with_history", "csv_export"]
    source_observed_at: str
    source_task_id: str
    source_schedule_id: str | None = None
    source_run_metadata: dict[str, Any]
    artifact_bucket: str
    artifact_path: str
    row_count: int
    artifact_checksum: str
    use_snapshot_replace: bool | None = None
    is_first_chunk: bool | None = None


# ---------------------------------------------------------------------------
# Helper (replicated from internal.py)
# ---------------------------------------------------------------------------

def _build_fmcsa_source_context(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
) -> dict[str, Any]:
    return {
        "feed_name": payload.feed_name,
        "feed_date": payload.feed_date,
        "download_url": payload.download_url,
        "source_file_variant": payload.source_file_variant,
        "source_observed_at": payload.source_observed_at,
        "source_task_id": payload.source_task_id,
        "source_schedule_id": payload.source_schedule_id,
        "source_run_metadata": payload.source_run_metadata,
        "use_snapshot_replace": payload.use_snapshot_replace,
        "is_first_chunk": payload.is_first_chunk,
    }


# ---------------------------------------------------------------------------
# Upsert-batch endpoints (18 tables)
# ---------------------------------------------------------------------------

@router.post("/operating-authority-histories/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_operating_authority_histories(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_operating_authority_histories(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/operating-authority-revocations/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_operating_authority_revocations(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_operating_authority_revocations(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/insurance-policies/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_insurance_policies(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_insurance_policies(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/insurance-policy-filings/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_insurance_policy_filings(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_insurance_policy_filings(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/insurance-policy-history-events/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_insurance_policy_history_events(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_insurance_policy_history_events(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/carrier-registrations/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_carrier_registrations(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_carrier_registrations(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/carrier-safety-basic-measures/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_carrier_safety_basic_measures(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_carrier_safety_basic_measures(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/commercial-vehicle-crashes/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_commercial_vehicle_crashes(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_commercial_vehicle_crashes(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/carrier-safety-basic-percentiles/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_carrier_safety_basic_percentiles(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_carrier_safety_basic_percentiles(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/vehicle-inspection-units/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_vehicle_inspection_units(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_vehicle_inspection_units(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/carrier-inspection-violations/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_carrier_inspection_violations(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_carrier_inspection_violations(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/vehicle-inspection-special-studies/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_vehicle_inspection_special_studies(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_vehicle_inspection_special_studies(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/carrier-inspections/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_carrier_inspections(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_carrier_inspections(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/vehicle-inspection-citations/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_vehicle_inspection_citations(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_vehicle_inspection_citations(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/motor-carrier-census-records/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_motor_carrier_census_records(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_motor_carrier_census_records(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/out-of-service-orders/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_out_of_service_orders(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_out_of_service_orders(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/process-agent-filings/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_process_agent_filings(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_process_agent_filings(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


@router.post("/insurance-filing-rejections/upsert-batch", response_model=DataEnvelope)
async def ingest_upsert_insurance_filing_rejections(
    payload: InternalUpsertFmcsaDailyDiffBatchRequest,
    _: None = Depends(require_internal_key),
):
    result = upsert_insurance_filing_rejections(
        source_context=_build_fmcsa_source_context(payload),
        rows=[row.model_dump() for row in payload.records],
    )
    return DataEnvelope(data=result)


# ---------------------------------------------------------------------------
# Artifact ingest endpoint
# ---------------------------------------------------------------------------

@router.post("/fmcsa/ingest-artifact", response_model=DataEnvelope)
async def ingest_fmcsa_artifact(
    payload: InternalFmcsaArtifactIngestRequest,
    _: None = Depends(require_internal_key),
):
    from app.services.fmcsa_artifact_ingest import (
        ChecksumMismatchError,
        ingest_artifact,
    )

    try:
        result = ingest_artifact(
            feed_name=payload.feed_name,
            feed_date=payload.feed_date,
            download_url=payload.download_url,
            source_file_variant=payload.source_file_variant,
            source_observed_at=payload.source_observed_at,
            source_task_id=payload.source_task_id,
            source_schedule_id=payload.source_schedule_id,
            source_run_metadata=payload.source_run_metadata,
            artifact_bucket=payload.artifact_bucket,
            artifact_path=payload.artifact_path,
            row_count=payload.row_count,
            artifact_checksum=payload.artifact_checksum,
            use_snapshot_replace=payload.use_snapshot_replace,
            is_first_chunk=payload.is_first_chunk,
        )
        return DataEnvelope(data=result)
    except ChecksumMismatchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
