from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
import json
import logging
import re
import time
from uuid import uuid4
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any, TypedDict

import threading

from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

_fmcsa_pool: ConnectionPool | None = None
_fmcsa_pool_lock = threading.Lock()

FMCSA_SOURCE_PROVIDER = "fmcsa_open_data"
FMCSA_ENTITIES_SCHEMA = "entities"
FMCSA_CONFLICT_COLUMNS = ("feed_date", "source_feed_name", "row_position")
FMCSA_LEGACY_CONFLICT_COLUMNS = ("record_fingerprint",)
FMCSA_INSERT_ONLY_ON_CONFLICT_COLUMNS = frozenset(
    {
        "created_at",
        "record_fingerprint",
        "first_observed_at",
    }
)
FMCSA_JSONB_COLUMNS = frozenset({"raw_source_row", "source_run_metadata"})
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
_COPY_NULL_TOKEN = r"\N"
_COPY_DELIMITER = "\t"
_COPY_ROW_DELIMITER = "\n"


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


def _get_fmcsa_connection_pool() -> ConnectionPool:
    global _fmcsa_pool
    if _fmcsa_pool is not None:
        return _fmcsa_pool
    with _fmcsa_pool_lock:
        if _fmcsa_pool is not None:
            return _fmcsa_pool
        settings = get_settings()
        _fmcsa_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=4,
            timeout=30.0,
        )
        return _fmcsa_pool


def get_fmcsa_direct_postgres_connection():
    return _get_fmcsa_connection_pool().getconn()


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


@lru_cache(maxsize=None)
def _get_table_columns(table_name: str) -> tuple[str, ...]:
    with _get_fmcsa_connection_pool().connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position
                """,
                (FMCSA_ENTITIES_SCHEMA, table_name),
            )
            return tuple(str(row[0]) for row in cursor.fetchall())


def _get_conflict_columns(*, available_columns: set[str]) -> tuple[str, ...]:
    if set(FMCSA_CONFLICT_COLUMNS).issubset(available_columns):
        return FMCSA_CONFLICT_COLUMNS
    if set(FMCSA_LEGACY_CONFLICT_COLUMNS).issubset(available_columns):
        return FMCSA_LEGACY_CONFLICT_COLUMNS
    raise ValueError(
        "FMCSA bulk upsert could not determine a valid conflict target for the live table schema"
    )


def _collect_insert_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for column_name in row:
            if column_name not in seen:
                seen.add(column_name)
                columns.append(column_name)
    return columns


def _build_fmcsa_bulk_merge_sql(
    *,
    table_name: str,
    temp_table_name: str,
    columns: list[str],
    conflict_columns: tuple[str, ...],
) -> str:
    quoted_columns = ", ".join(_quote_identifier(column_name) for column_name in columns)
    projected_columns = ", ".join(_quote_identifier(column_name) for column_name in columns)
    quoted_conflict_columns = ", ".join(_quote_identifier(column_name) for column_name in conflict_columns)

    update_assignments = [
        f'{_quote_identifier(column_name)} = EXCLUDED.{_quote_identifier(column_name)}'
        for column_name in columns
        if column_name not in conflict_columns
        and column_name not in FMCSA_INSERT_ONLY_ON_CONFLICT_COLUMNS
    ]
    if not update_assignments:
        raise ValueError(f"FMCSA bulk upsert for {table_name} has no mutable columns")

    return (
        f"INSERT INTO {_quote_qualified_identifier(FMCSA_ENTITIES_SCHEMA, table_name)} "
        f"({quoted_columns}) SELECT {projected_columns} "
        f"FROM {_quote_identifier(temp_table_name)} "
        f"ON CONFLICT ({quoted_conflict_columns}) DO UPDATE SET "
        f"{', '.join(update_assignments)}"
    )


def _build_temp_table_name(table_name: str) -> str:
    sanitized_table_name = re.sub(r"[^A-Za-z0-9_]", "_", table_name)
    suffix = uuid4().hex[:8]
    max_table_name_length = 63 - len("tmp_fmcsa__") - len(suffix)
    truncated_table_name = sanitized_table_name[:max_table_name_length]
    return f"tmp_fmcsa_{truncated_table_name}_{suffix}"


def _create_temp_staging_table(*, cursor: Any, table_name: str, temp_table_name: str) -> None:
    cursor.execute(
        f"CREATE TEMP TABLE {_quote_identifier(temp_table_name)} "
        f"(LIKE {_quote_qualified_identifier(FMCSA_ENTITIES_SCHEMA, table_name)} INCLUDING DEFAULTS) "
        "ON COMMIT DROP"
    )


def _serialize_jsonb_copy_value(value: dict[str, Any] | list[Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _escape_copy_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _serialize_copy_value(*, column_name: str, value: Any) -> str:
    if value is None:
        return _COPY_NULL_TOKEN
    if column_name in FMCSA_JSONB_COLUMNS and isinstance(value, (dict, list)):
        text_value = _serialize_jsonb_copy_value(value)
    elif isinstance(value, bool):
        text_value = "t" if value else "f"
    elif isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        text_value = value.astimezone(timezone.utc).isoformat()
    elif isinstance(value, date):
        text_value = value.isoformat()
    else:
        text_value = str(value)
    return _escape_copy_text(text_value)


def _build_copy_payload(*, rows: list[dict[str, Any]], columns: list[str]) -> str:
    serialized_rows: list[str] = []
    for row in rows:
        serialized_rows.append(
            _COPY_DELIMITER.join(
                _serialize_copy_value(column_name=column_name, value=row.get(column_name))
                for column_name in columns
            )
        )
    return f"{_COPY_ROW_DELIMITER.join(serialized_rows)}{_COPY_ROW_DELIMITER}"


def _copy_rows_into_temp_table(
    *,
    cursor: Any,
    temp_table_name: str,
    rows: list[dict[str, Any]],
    columns: list[str],
) -> None:
    quoted_columns = ", ".join(_quote_identifier(column_name) for column_name in columns)
    copy_sql = (
        f"COPY {_quote_identifier(temp_table_name)} ({quoted_columns}) "
        "FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')"
    )
    copy_payload = _build_copy_payload(rows=rows, columns=columns)
    with cursor.copy(copy_sql) as copy:
        copy.write(copy_payload)


def _drop_temp_table_if_exists(*, connection: Any, temp_table_name: str) -> None:
    with connection.cursor() as cleanup_cursor:
        cleanup_cursor.execute(f'DROP TABLE IF EXISTS {_quote_identifier(temp_table_name)}')


def upsert_fmcsa_daily_diff_rows(
    *,
    table_name: str,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
    row_builder: Callable[[FmcsaDailyDiffRow], dict[str, Any]],
) -> dict[str, Any]:
    t_total_start = time.perf_counter()
    phases: dict[str, Any] = {
        "table_name": table_name,
        "feed_date": source_context["feed_date"],
        "rows_received": len(rows),
        "rows_written": 0,
        "error": False,
    }

    try:
        now = utc_now_iso()
        source_observed_at = source_context["source_observed_at"]
        live_table_columns = set(_get_table_columns(table_name))

        t_row_builder_start = time.perf_counter()
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
            if table_name in FMCSA_SNAPSHOT_HISTORY_TABLES and (
                not live_table_columns or "record_fingerprint" in live_table_columns
            ):
                insert_row["record_fingerprint"] = _build_record_fingerprint(
                    table_name=table_name,
                    feed_date=source_context["feed_date"],
                    feed_name=source_context["feed_name"],
                    row_position=row["row_number"],
                )
            if table_name in FMCSA_SNAPSHOT_HISTORY_TABLES and (
                not live_table_columns or "first_observed_at" in live_table_columns
            ):
                insert_row["first_observed_at"] = source_observed_at
            if table_name in FMCSA_SNAPSHOT_HISTORY_TABLES and (
                not live_table_columns or "last_observed_at" in live_table_columns
            ):
                insert_row["last_observed_at"] = source_observed_at
            upsert_rows.append(insert_row)
        phases["row_builder_ms"] = round((time.perf_counter() - t_row_builder_start) * 1000, 1)

        if not upsert_rows:
            phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
            logger.info("fmcsa_batch_persist_phases", extra=phases)
            return {
                "feed_name": source_context["feed_name"],
                "table_name": table_name,
                "feed_date": source_context["feed_date"],
                "rows_received": len(rows),
                "rows_written": 0,
            }

        if live_table_columns:
            upsert_rows = [
                {
                    column_name: row_value
                    for column_name, row_value in row.items()
                    if column_name in live_table_columns
                }
                for row in upsert_rows
            ]
        columns = _collect_insert_columns(upsert_rows)
        conflict_columns = (
            _get_conflict_columns(available_columns=set(columns))
            if live_table_columns
            else FMCSA_CONFLICT_COLUMNS
        )
        temp_table_name = _build_temp_table_name(table_name)
        upsert_sql = _build_fmcsa_bulk_merge_sql(
            table_name=table_name,
            temp_table_name=temp_table_name,
            columns=columns,
            conflict_columns=conflict_columns,
        )

        pool = _get_fmcsa_connection_pool()
        t_conn_start = time.perf_counter()
        with pool.connection() as connection:
            phases["connection_acquire_ms"] = round((time.perf_counter() - t_conn_start) * 1000, 1)
            try:
                with connection.cursor() as cursor:
                    t_temp = time.perf_counter()
                    _create_temp_staging_table(
                        cursor=cursor,
                        table_name=table_name,
                        temp_table_name=temp_table_name,
                    )
                    phases["temp_table_create_ms"] = round((time.perf_counter() - t_temp) * 1000, 1)

                    t_copy = time.perf_counter()
                    _copy_rows_into_temp_table(
                        cursor=cursor,
                        temp_table_name=temp_table_name,
                        rows=upsert_rows,
                        columns=columns,
                    )
                    phases["copy_ms"] = round((time.perf_counter() - t_copy) * 1000, 1)

                    t_merge = time.perf_counter()
                    cursor.execute(upsert_sql)
                    phases["merge_ms"] = round((time.perf_counter() - t_merge) * 1000, 1)

                t_commit = time.perf_counter()
                connection.commit()
                phases["commit_ms"] = round((time.perf_counter() - t_commit) * 1000, 1)
            except Exception:
                try:
                    connection.rollback()
                finally:
                    try:
                        _drop_temp_table_if_exists(
                            connection=connection,
                            temp_table_name=temp_table_name,
                        )
                    except Exception:
                        pass
                raise

        phases["rows_written"] = len(upsert_rows)
        phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
        logger.info("fmcsa_batch_persist_phases", extra=phases)

        return {
            "feed_name": source_context["feed_name"],
            "table_name": table_name,
            "feed_date": source_context["feed_date"],
            "rows_received": len(rows),
            "rows_written": len(upsert_rows),
        }
    except Exception:
        phases["error"] = True
        phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
        logger.info("fmcsa_batch_persist_phases", extra=phases)
        raise
