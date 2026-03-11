from __future__ import annotations

from hashlib import sha256
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypedDict

from psycopg import connect
from psycopg.types.json import Jsonb

from app.config import get_settings

FMCSA_SOURCE_PROVIDER = "fmcsa_open_data"
FMCSA_ENTITIES_SCHEMA = "entities"
FMCSA_CONFLICT_COLUMNS = ("feed_date", "source_feed_name", "row_position")
FMCSA_INSERT_ONLY_ON_CONFLICT_COLUMNS = frozenset(
    {
        "created_at",
        "record_fingerprint",
        "first_observed_at",
    }
)
FMCSA_SNAPSHOT_HISTORY_TABLES = frozenset(
    {
        "operating_authority_histories",
        "operating_authority_revocations",
        "insurance_policies",
        "insurance_policy_filings",
        "insurance_policy_history_events",
    }
)
_SQL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def get_fmcsa_direct_postgres_connection():
    settings = get_settings()
    return connect(settings.database_url)


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


def _quote_identifier(identifier: str) -> str:
    if not _SQL_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _quote_qualified_identifier(*parts: str) -> str:
    return ".".join(_quote_identifier(part) for part in parts)


def _build_record_fingerprint(
    *,
    table_name: str,
    feed_date: str,
    feed_name: str,
    row_position: int,
) -> str:
    identity = f"{table_name}|{feed_date}|{feed_name}|{row_position}"
    return sha256(identity.encode("utf-8")).hexdigest()


def _collect_insert_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for column_name in row:
            if column_name not in seen:
                seen.add(column_name)
                columns.append(column_name)
    return columns


def _adapt_postgres_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return Jsonb(value)
    return value


def _normalize_postgres_rows(
    *,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> list[dict[str, Any]]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized_rows.append(
            {
                column_name: _adapt_postgres_value(row.get(column_name))
                for column_name in columns
            }
        )
    return normalized_rows


def _build_fmcsa_bulk_upsert_sql(*, table_name: str, columns: list[str]) -> str:
    quoted_columns = ", ".join(_quote_identifier(column_name) for column_name in columns)
    placeholders = ", ".join(f"%({column_name})s" for column_name in columns)
    quoted_conflict_columns = ", ".join(
        _quote_identifier(column_name) for column_name in FMCSA_CONFLICT_COLUMNS
    )

    update_assignments = [
        f'{_quote_identifier(column_name)} = EXCLUDED.{_quote_identifier(column_name)}'
        for column_name in columns
        if column_name not in FMCSA_CONFLICT_COLUMNS
        and column_name not in FMCSA_INSERT_ONLY_ON_CONFLICT_COLUMNS
    ]
    if not update_assignments:
        raise ValueError(f"FMCSA bulk upsert for {table_name} has no mutable columns")

    return (
        f"INSERT INTO { _quote_qualified_identifier(FMCSA_ENTITIES_SCHEMA, table_name) } "
        f"({quoted_columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({quoted_conflict_columns}) DO UPDATE SET "
        f"{', '.join(update_assignments)}"
    )


def upsert_fmcsa_daily_diff_rows(
    *,
    table_name: str,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
    row_builder: Callable[[FmcsaDailyDiffRow], dict[str, Any]],
) -> dict[str, Any]:
    now = utc_now_iso()
    source_observed_at = source_context["source_observed_at"]
    upsert_rows: list[dict[str, Any]] = []
    for row in rows:
        typed_row = row_builder(row)
        insert_row = {
            **typed_row,
            "feed_date": source_context["feed_date"],
            "row_position": row["row_number"],
            "source_provider": FMCSA_SOURCE_PROVIDER,
            "source_feed_name": source_context["feed_name"],
            "source_download_url": source_context["download_url"],
            "source_file_variant": source_context["source_file_variant"],
            "source_observed_at": source_observed_at,
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
        if table_name in FMCSA_SNAPSHOT_HISTORY_TABLES:
            insert_row["record_fingerprint"] = _build_record_fingerprint(
                table_name=table_name,
                feed_date=source_context["feed_date"],
                feed_name=source_context["feed_name"],
                row_position=row["row_number"],
            )
            insert_row["first_observed_at"] = source_observed_at
            insert_row["last_observed_at"] = source_observed_at
        upsert_rows.append(insert_row)

    if not upsert_rows:
        return {
            "feed_name": source_context["feed_name"],
            "table_name": table_name,
            "feed_date": source_context["feed_date"],
            "rows_received": len(rows),
            "rows_written": 0,
        }

    columns = _collect_insert_columns(upsert_rows)
    postgres_rows = _normalize_postgres_rows(rows=upsert_rows, columns=columns)
    upsert_sql = _build_fmcsa_bulk_upsert_sql(table_name=table_name, columns=columns)

    with get_fmcsa_direct_postgres_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany(upsert_sql, postgres_rows)

    return {
        "feed_name": source_context["feed_name"],
        "table_name": table_name,
        "feed_date": source_context["feed_date"],
        "rows_received": len(rows),
        "rows_written": len(upsert_rows),
    }
