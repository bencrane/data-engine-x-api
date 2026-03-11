from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypedDict

from app.database import get_supabase_client

FMCSA_SOURCE_PROVIDER = "fmcsa_open_data"


class FmcsaDailyDiffRow(TypedDict):
    row_number: int
    raw_values: list[str]
    raw_fields: dict[str, str]


class FmcsaSourceContext(TypedDict):
    feed_name: str
    feed_date: str
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


def parse_yyyymmdd_date(value: Any) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    try:
        return datetime.strptime(cleaned, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def parse_iso_date(value: Any) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    try:
        return datetime.strptime(cleaned, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def parse_fmcsa_date(value: Any) -> str | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None

    for date_format in ("%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y"):
        try:
            return datetime.strptime(cleaned, date_format).date().isoformat()
        except ValueError:
            continue

    return None


def parse_int(value: Any) -> int | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_float(value: Any) -> float | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_bool(value: Any) -> bool | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None

    normalized = cleaned.lower()
    if normalized in {"true", "t", "yes", "y", "1"}:
        return True
    if normalized in {"false", "f", "no", "n", "0"}:
        return False
    return None


def parse_x_flag(value: Any) -> bool | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    return cleaned.upper() == "X"


def is_blank_or_zero(value: Any) -> bool:
    cleaned = clean_text(value)
    if cleaned is None:
        return True
    return all(character == "0" for character in cleaned)


def upsert_fmcsa_daily_diff_rows(
    *,
    table_name: str,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
    row_builder: Callable[[FmcsaDailyDiffRow], dict[str, Any]],
) -> dict[str, Any]:
    now = utc_now_iso()
    upsert_rows: list[dict[str, Any]] = []
    for row in rows:
        typed_row = row_builder(row)
        upsert_rows.append(
            {
                **typed_row,
                "feed_date": source_context["feed_date"],
                "row_position": row["row_number"],
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
                "updated_at": now,
            }
        )

    if not upsert_rows:
        return {
            "feed_name": source_context["feed_name"],
            "table_name": table_name,
            "feed_date": source_context["feed_date"],
            "rows_received": len(rows),
            "rows_written": 0,
        }

    result = get_supabase_client().table(table_name).upsert(
        upsert_rows,
        on_conflict="feed_date,source_feed_name,row_position",
    ).execute()

    return {
        "feed_name": source_context["feed_name"],
        "table_name": table_name,
        "feed_date": source_context["feed_date"],
        "rows_received": len(rows),
        "rows_written": len(result.data or []),
    }
