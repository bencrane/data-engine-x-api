from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, TypedDict

from app.database import get_supabase_client

FMCSA_SOURCE_PROVIDER = "fmcsa_open_data"


class FmcsaDailyDiffRow(TypedDict):
    row_number: int
    raw_values: list[str]
    raw_fields: dict[str, str]


class FmcsaSourceContext(TypedDict):
    feed_name: str
    download_url: str
    source_file_variant: str
    source_observed_at: str
    source_task_id: str
    source_schedule_id: str | None
    source_run_metadata: dict[str, Any]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    cleaned = str(value).strip()
    return cleaned or None


def parse_mmddyyyy_date(value: Any) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    try:
        return datetime.strptime(cleaned, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def is_blank_or_zero(value: Any) -> bool:
    cleaned = clean_text(value)
    if cleaned is None:
        return True
    return all(character == "0" for character in cleaned)


def fingerprint_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value.strip().lower()
    return str(value).strip().lower()


def build_record_fingerprint(**parts: Any) -> str:
    normalized = {key: fingerprint_value(value) for key, value in parts.items()}
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def chunked(values: Iterable[str], size: int) -> Iterable[list[str]]:
    batch: list[str] = []
    for value in values:
        batch.append(value)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def upsert_fmcsa_daily_diff_rows(
    *,
    table_name: str,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
    row_builder: Callable[[FmcsaDailyDiffRow], dict[str, Any]],
) -> dict[str, Any]:
    now = utc_now_iso()
    deduped_rows: dict[str, dict[str, Any]] = {}

    for row in rows:
        typed_row = row_builder(row)
        record_fingerprint = typed_row["record_fingerprint"]

        deduped_rows[record_fingerprint] = {
            **typed_row,
            "source_provider": FMCSA_SOURCE_PROVIDER,
            "source_feed_name": source_context["feed_name"],
            "source_download_url": source_context["download_url"],
            "source_file_variant": source_context["source_file_variant"],
            "source_observed_at": source_context["source_observed_at"],
            "source_task_id": source_context["source_task_id"],
            "source_schedule_id": source_context["source_schedule_id"],
            "source_run_metadata": source_context["source_run_metadata"],
            "raw_source_row": {
                "row_number": row["row_number"],
                "raw_values": row["raw_values"],
                "raw_fields": row["raw_fields"],
            },
            "last_observed_at": source_context["source_observed_at"],
            "updated_at": now,
        }

    fingerprints = list(deduped_rows.keys())
    existing_first_observed_at: dict[str, str] = {}

    client = get_supabase_client()
    for fingerprint_batch in chunked(fingerprints, 500):
        existing_result = (
            client.table(table_name)
            .select("record_fingerprint,first_observed_at")
            .in_("record_fingerprint", fingerprint_batch)
            .execute()
        )
        for existing_row in existing_result.data or []:
            record_fingerprint = existing_row.get("record_fingerprint")
            first_observed_at = existing_row.get("first_observed_at")
            if isinstance(record_fingerprint, str) and isinstance(first_observed_at, str):
                existing_first_observed_at[record_fingerprint] = first_observed_at

    upsert_rows: list[dict[str, Any]] = []
    for record_fingerprint, row in deduped_rows.items():
        upsert_rows.append(
            {
                **row,
                "first_observed_at": existing_first_observed_at.get(
                    record_fingerprint,
                    source_context["source_observed_at"],
                ),
            }
        )

    if not upsert_rows:
        return {
            "feed_name": source_context["feed_name"],
            "table_name": table_name,
            "rows_received": len(rows),
            "unique_rows": 0,
            "rows_written": 0,
            "inserted_count": 0,
            "updated_count": 0,
        }

    result = client.table(table_name).upsert(upsert_rows, on_conflict="record_fingerprint").execute()

    updated_count = sum(1 for fingerprint in fingerprints if fingerprint in existing_first_observed_at)
    inserted_count = len(upsert_rows) - updated_count

    return {
        "feed_name": source_context["feed_name"],
        "table_name": table_name,
        "rows_received": len(rows),
        "unique_rows": len(upsert_rows),
        "rows_written": len(result.data or []),
        "inserted_count": inserted_count,
        "updated_count": updated_count,
    }
