# app/services/fmcsa_artifact_ingest.py — FMCSA staged artifact ingest service

from __future__ import annotations

import gzip
import hashlib
import io
import json
import logging
import time
from typing import Any, Callable

from app.config import get_settings
from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    upsert_fmcsa_daily_diff_rows,
)

# Per-feed service upsert functions (each handles table_name + row_builder internally)
from app.services.carrier_inspections import upsert_carrier_inspections
from app.services.carrier_inspection_violations import upsert_carrier_inspection_violations
from app.services.carrier_registrations import upsert_carrier_registrations
from app.services.carrier_safety_basic_measures import upsert_carrier_safety_basic_measures
from app.services.carrier_safety_basic_percentiles import upsert_carrier_safety_basic_percentiles
from app.services.commercial_vehicle_crashes import upsert_commercial_vehicle_crashes
from app.services.insurance_filing_rejections import upsert_insurance_filing_rejections
from app.services.insurance_policies import upsert_insurance_policies
from app.services.insurance_policy_filings import upsert_insurance_policy_filings
from app.services.insurance_policy_history_events import upsert_insurance_policy_history_events
from app.services.motor_carrier_census_records import upsert_motor_carrier_census_records
from app.services.operating_authority_histories import upsert_operating_authority_histories
from app.services.operating_authority_revocations import upsert_operating_authority_revocations
from app.services.out_of_service_orders import upsert_out_of_service_orders
from app.services.process_agent_filings import upsert_process_agent_filings
from app.services.vehicle_inspection_citations import upsert_vehicle_inspection_citations
from app.services.vehicle_inspection_special_studies import upsert_vehicle_inspection_special_studies
from app.services.vehicle_inspection_units import upsert_vehicle_inspection_units

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 50_000

# Type for per-feed upsert functions: takes source_context + rows, returns result dict
FmcsaUpsertFunc = Callable[..., dict[str, Any]]

# Registry: feed_name -> (table_name, upsert_function)
# The upsert function handles row_builder selection internally (including carrier_segment
# disambiguation and feed-variant-specific row builders).
FMCSA_FEED_REGISTRY: dict[str, tuple[str, FmcsaUpsertFunc]] = {
    # Daily diff feeds
    "AuthHist": ("operating_authority_histories", upsert_operating_authority_histories),
    "Revocation": ("operating_authority_revocations", upsert_operating_authority_revocations),
    "Insurance": ("insurance_policies", upsert_insurance_policies),
    "ActPendInsur": ("insurance_policy_filings", upsert_insurance_policy_filings),
    "InsHist": ("insurance_policy_history_events", upsert_insurance_policy_history_events),
    # Plain text daily feeds
    "Carrier": ("carrier_registrations", upsert_carrier_registrations),
    "Rejected": ("insurance_filing_rejections", upsert_insurance_filing_rejections),
    "BOC3": ("process_agent_filings", upsert_process_agent_filings),
    # All-with-history feeds (share tables with daily diff counterparts)
    "InsHist - All With History": ("insurance_policy_history_events", upsert_insurance_policy_history_events),
    "BOC3 - All With History": ("process_agent_filings", upsert_process_agent_filings),
    "ActPendInsur - All With History": ("insurance_policy_filings", upsert_insurance_policy_filings),
    "Rejected - All With History": ("insurance_filing_rejections", upsert_insurance_filing_rejections),
    "AuthHist - All With History": ("operating_authority_histories", upsert_operating_authority_histories),
    "Carrier - All With History": ("carrier_registrations", upsert_carrier_registrations),
    "Revocation - All With History": ("operating_authority_revocations", upsert_operating_authority_revocations),
    "Insur - All With History": ("insurance_policies", upsert_insurance_policies),
    # CSV export feeds
    "Crash File": ("commercial_vehicle_crashes", upsert_commercial_vehicle_crashes),
    "Inspections Per Unit": ("vehicle_inspection_units", upsert_vehicle_inspection_units),
    "Special Studies": ("vehicle_inspection_special_studies", upsert_vehicle_inspection_special_studies),
    "OUT OF SERVICE ORDERS": ("out_of_service_orders", upsert_out_of_service_orders),
    "Inspections and Citations": ("vehicle_inspection_citations", upsert_vehicle_inspection_citations),
    "Vehicle Inspections and Violations": ("carrier_inspection_violations", upsert_carrier_inspection_violations),
    "Company Census File": ("motor_carrier_census_records", upsert_motor_carrier_census_records),
    "Vehicle Inspection File": ("carrier_inspections", upsert_carrier_inspections),
    # SMS feeds
    "SMS AB PassProperty": ("carrier_safety_basic_measures", upsert_carrier_safety_basic_measures),
    "SMS C PassProperty": ("carrier_safety_basic_measures", upsert_carrier_safety_basic_measures),
    "SMS Input - Violation": ("carrier_inspection_violations", upsert_carrier_inspection_violations),
    "SMS Input - Inspection": ("carrier_inspections", upsert_carrier_inspections),
    "SMS Input - Motor Carrier Census": ("motor_carrier_census_records", upsert_motor_carrier_census_records),
    "SMS AB Pass": ("carrier_safety_basic_percentiles", upsert_carrier_safety_basic_percentiles),
    "SMS C Pass": ("carrier_safety_basic_percentiles", upsert_carrier_safety_basic_percentiles),
}


def download_artifact_from_storage(
    bucket: str,
    path: str,
) -> bytes:
    """Download a gzipped artifact from Supabase Storage. Returns raw gzipped bytes."""
    settings = get_settings()
    # Use direct HTTP to avoid buffering issues with the Supabase Python client
    import httpx

    url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_key}",
        "apikey": settings.supabase_service_key,
    }
    response = httpx.get(url, headers=headers, timeout=600.0)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to download artifact from {bucket}/{path}: HTTP {response.status_code} - {response.text[:500]}"
        )
    return response.content


def verify_checksum(data: bytes, expected_checksum: str) -> bool:
    """Verify SHA-256 checksum of data against expected hex digest."""
    actual = hashlib.sha256(data).hexdigest()
    return actual == expected_checksum


def parse_ndjson_rows(
    decompressed_data: bytes,
) -> list[FmcsaDailyDiffRow]:
    """Parse NDJSON bytes into a list of FmcsaDailyDiffRow dicts, streaming line by line."""
    rows: list[FmcsaDailyDiffRow] = []
    for line in decompressed_data.split(b"\n"):
        line = line.strip()
        if not line:
            continue
        parsed = json.loads(line)
        rows.append(parsed)
    return rows


def ingest_artifact(
    *,
    feed_name: str,
    feed_date: str,
    download_url: str,
    source_file_variant: str,
    source_observed_at: str,
    source_task_id: str,
    source_schedule_id: str | None,
    source_run_metadata: dict[str, Any],
    artifact_bucket: str,
    artifact_path: str,
    row_count: int,
    artifact_checksum: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    use_snapshot_replace: bool | None = None,
    is_first_chunk: bool | None = None,
) -> dict[str, Any]:
    """
    Download artifact from Supabase Storage, verify checksum, decompress,
    parse NDJSON, and persist rows through existing per-feed upsert pipeline in chunks.
    """
    total_start = time.monotonic()

    # Resolve feed
    registry_entry = FMCSA_FEED_REGISTRY.get(feed_name)
    if registry_entry is None:
        raise ValueError(f"Unknown FMCSA feed_name: {feed_name!r}")
    table_name, upsert_func = registry_entry

    # Download artifact
    download_start = time.monotonic()
    gzipped_bytes = download_artifact_from_storage(artifact_bucket, artifact_path)
    artifact_download_ms = (time.monotonic() - download_start) * 1000

    # Verify checksum
    if not verify_checksum(gzipped_bytes, artifact_checksum):
        actual_checksum = hashlib.sha256(gzipped_bytes).hexdigest()
        raise ChecksumMismatchError(
            f"Artifact checksum mismatch for {artifact_path}: "
            f"expected {artifact_checksum}, got {actual_checksum}"
        )

    if use_snapshot_replace is None:
        use_snapshot_replace = source_file_variant == "csv_export"

    # Build source context
    source_context: FmcsaSourceContext = {
        "feed_name": feed_name,
        "feed_date": feed_date,
        "download_url": download_url,
        "source_file_variant": source_file_variant,
        "source_observed_at": source_observed_at,
        "source_task_id": source_task_id,
        "source_schedule_id": source_schedule_id,
        "source_run_metadata": source_run_metadata,
        "use_snapshot_replace": use_snapshot_replace,
    }

    # Streaming decompress → parse → persist in chunks.
    # Instead of materializing the entire decompressed artifact + full row list,
    # we stream lines from GzipFile and persist each chunk as it fills.
    #
    # When is_first_chunk is supplied by the caller (streaming chunked uploads from
    # Trigger), we honour it for the first internal sub-chunk only, and set False
    # for all subsequent sub-chunks. When not supplied, we fall back to the original
    # behaviour (first internal chunk = True).
    caller_is_first_chunk = is_first_chunk

    total_rows_parsed = 0
    total_rows_written = 0
    chunks_processed = 0
    chunk: list[FmcsaDailyDiffRow] = []

    stream_start = time.monotonic()
    total_persist_ms = 0.0

    bio = io.BytesIO(gzipped_bytes)
    with gzip.GzipFile(fileobj=bio) as gzip_file:
        for line in gzip_file:
            line = line.strip()
            if not line:
                continue
            chunk.append(json.loads(line))
            total_rows_parsed += 1

            if len(chunk) == chunk_size:
                chunk_number = chunks_processed + 1
                persist_chunk_start = time.monotonic()
                if caller_is_first_chunk is not None:
                    source_context["is_first_chunk"] = caller_is_first_chunk and (chunks_processed == 0)
                else:
                    source_context["is_first_chunk"] = (chunks_processed == 0)
                try:
                    result = upsert_func(
                        source_context=source_context,
                        rows=chunk,
                    )
                    total_rows_written += result.get("rows_written", 0)
                    chunks_processed += 1
                except Exception as exc:
                    logger.error(
                        "fmcsa_artifact_ingest_chunk_failed",
                        extra={
                            "feed_name": feed_name,
                            "feed_date": feed_date,
                            "table_name": table_name,
                            "artifact_path": artifact_path,
                            "chunk_number": chunk_number,
                            "rows_processed_so_far": total_rows_written,
                            "error": str(exc),
                        },
                    )
                    raise RuntimeError(
                        f"FMCSA artifact ingest failed at chunk {chunk_number} "
                        f"(rows {total_rows_parsed - len(chunk)}-{total_rows_parsed}) for {feed_name}: {exc}"
                    ) from exc
                total_persist_ms += (time.monotonic() - persist_chunk_start) * 1000
                chunk = []

    # Flush remaining partial chunk
    if chunk:
        chunk_number = chunks_processed + 1
        persist_chunk_start = time.monotonic()
        if caller_is_first_chunk is not None:
            source_context["is_first_chunk"] = caller_is_first_chunk and (chunks_processed == 0)
        else:
            source_context["is_first_chunk"] = (chunks_processed == 0)
        try:
            result = upsert_func(
                source_context=source_context,
                rows=chunk,
            )
            total_rows_written += result.get("rows_written", 0)
            chunks_processed += 1
        except Exception as exc:
            logger.error(
                "fmcsa_artifact_ingest_chunk_failed",
                extra={
                    "feed_name": feed_name,
                    "feed_date": feed_date,
                    "table_name": table_name,
                    "artifact_path": artifact_path,
                    "chunk_number": chunk_number,
                    "rows_processed_so_far": total_rows_written,
                    "error": str(exc),
                },
            )
            raise RuntimeError(
                f"FMCSA artifact ingest failed at chunk {chunk_number} "
                f"(rows {total_rows_parsed - len(chunk)}-{total_rows_parsed}) for {feed_name}: {exc}"
            ) from exc
        total_persist_ms += (time.monotonic() - persist_chunk_start) * 1000

    artifact_decompress_parse_ms = (time.monotonic() - stream_start) * 1000
    total_ms = (time.monotonic() - total_start) * 1000

    logger.info(
        "fmcsa_artifact_ingest_summary",
        extra={
            "feed_name": feed_name,
            "feed_date": feed_date,
            "table_name": table_name,
            "artifact_path": artifact_path,
            "total_rows_received": total_rows_parsed,
            "total_rows_written": total_rows_written,
            "chunks_processed": chunks_processed,
            "artifact_download_ms": round(artifact_download_ms, 1),
            "artifact_decompress_parse_ms": round(artifact_decompress_parse_ms, 1),
            "total_persist_ms": round(total_persist_ms, 1),
            "total_ms": round(total_ms, 1),
        },
    )

    return {
        "feed_name": feed_name,
        "table_name": table_name,
        "feed_date": feed_date,
        "rows_received": total_rows_parsed,
        "rows_written": total_rows_written,
        "checksum_verified": True,
    }


class ChecksumMismatchError(Exception):
    """Raised when artifact checksum does not match expected value."""
    pass
