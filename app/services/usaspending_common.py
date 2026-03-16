# app/services/usaspending_common.py — USASpending.gov bulk persistence utilities
#
# Follows the proven COPY-based bulk write pattern from sam_gov_common.py,
# adapted for USASpending.gov comma-delimited CSV contract transaction files.

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, TypedDict
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.services.usaspending_column_map import (
    USASPENDING_COLUMN_COUNT,
    USASPENDING_CSV_TO_DB_MAP,
    USASPENDING_DB_COLUMN_NAMES,
    USASPENDING_DELTA_COLUMN_COUNT,
    USASPENDING_DELTA_EXTRA_COLUMNS,
)

logger = logging.getLogger(__name__)

_usaspending_pool: ConnectionPool | None = None
_usaspending_pool_lock = threading.Lock()

USASPENDING_TABLE_NAME = "usaspending_contracts"
USASPENDING_SCHEMA = "entities"
USASPENDING_CONFLICT_COLUMNS = ("extract_date", "contract_transaction_unique_key")
USASPENDING_INSERT_ONLY_ON_CONFLICT_COLUMNS = frozenset({"created_at"})

_SQL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COPY_NULL_TOKEN = r"\N"
_COPY_DELIMITER = "\t"
_COPY_ROW_DELIMITER = "\n"


class UsaspendingSourceContext(TypedDict):
    extract_date: str       # YYYY-MM-DD
    extract_type: str       # FULL or DELTA
    source_filename: str    # original CSV filename


class UsaspendingCsvRow(TypedDict):
    row_number: int
    fields: dict[str, str]  # CSV header -> value mapping


def _get_usaspending_connection_pool() -> ConnectionPool:
    global _usaspending_pool
    if _usaspending_pool is not None:
        return _usaspending_pool
    with _usaspending_pool_lock:
        if _usaspending_pool is not None:
            return _usaspending_pool
        settings = get_settings()
        _usaspending_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=4,
            timeout=30.0,
        )
        return _usaspending_pool


def _quote_identifier(identifier: str) -> str:
    if not _SQL_IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")
    return f'"{identifier}"'


def _quote_qualified_identifier(*parts: str) -> str:
    return ".".join(_quote_identifier(part) for part in parts)


def _escape_copy_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _serialize_copy_value(value: Any) -> str:
    if value is None:
        return _COPY_NULL_TOKEN
    text_value = str(value)
    return _escape_copy_text(text_value)


def parse_usaspending_csv_row(
    row_dict: dict[str, str],
    row_number: int,
    is_delta: bool = False,
) -> UsaspendingCsvRow | None:
    """Parse a single row from csv.DictReader output.

    Returns UsaspendingCsvRow on success, None on validation failure (logged).
    """
    expected_count = USASPENDING_DELTA_COLUMN_COUNT if is_delta else USASPENDING_COLUMN_COUNT
    actual_count = len(row_dict)

    if actual_count != expected_count:
        logger.warning(
            "usaspending_parse_field_count_mismatch",
            extra={
                "row_number": row_number,
                "expected_fields": expected_count,
                "actual_fields": actual_count,
                "is_delta": is_delta,
            },
        )
        return None

    # For delta files, the transaction key is under the same CSV header name
    txn_key = row_dict.get("contract_transaction_unique_key", "").strip()
    if not txn_key:
        logger.warning(
            "usaspending_parse_missing_txn_key",
            extra={"row_number": row_number, "is_delta": is_delta},
        )
        return None

    return UsaspendingCsvRow(
        row_number=row_number,
        fields=row_dict,
    )


def build_usaspending_contract_row(
    row: UsaspendingCsvRow,
    source_context: UsaspendingSourceContext,
    is_delta: bool = False,
) -> dict[str, Any]:
    """Map CSV header names to db_column_names and add extract metadata."""
    result: dict[str, Any] = {}

    # Map the 297 standard CSV columns to db column names
    for csv_header, db_col_name in USASPENDING_CSV_TO_DB_MAP.items():
        raw_value = row["fields"].get(csv_header, "")
        cleaned = raw_value.strip() if raw_value else None
        result[db_col_name] = cleaned if cleaned else None

    # Handle delta-only columns
    if is_delta:
        for delta_col in USASPENDING_DELTA_EXTRA_COLUMNS:
            csv_name = delta_col["csv_header_name"]
            db_name = delta_col["db_column_name"]
            raw_value = row["fields"].get(csv_name, "")
            cleaned = raw_value.strip() if raw_value else None
            result[db_name] = cleaned if cleaned else None
    else:
        result["correction_delete_ind"] = None
        result["agency_id"] = None

    # Add extract metadata
    result["extract_date"] = source_context["extract_date"]
    result["extract_type"] = source_context["extract_type"]
    result["source_filename"] = source_context["source_filename"]
    result["source_provider"] = "usaspending"
    result["row_position"] = row["row_number"]

    return result


def upsert_usaspending_contracts(
    *,
    source_context: UsaspendingSourceContext,
    rows: list[UsaspendingCsvRow],
    is_delta: bool = False,
) -> dict[str, Any]:
    """Bulk upsert USASpending contract rows using the COPY-based staging pattern."""
    t_total_start = time.perf_counter()
    phases: dict[str, Any] = {
        "table_name": USASPENDING_TABLE_NAME,
        "extract_date": source_context["extract_date"],
        "rows_received": len(rows),
        "rows_written": 0,
        "error": False,
    }

    try:
        # Phase 1: Build typed rows and deduplicate by conflict key
        t_row_builder_start = time.perf_counter()
        dedup: dict[tuple[str, ...], dict[str, Any]] = {}
        for row in rows:
            typed_row = build_usaspending_contract_row(row, source_context, is_delta=is_delta)
            conflict_key = tuple(
                str(typed_row.get(c, "")) for c in USASPENDING_CONFLICT_COLUMNS
            )
            dedup[conflict_key] = typed_row  # last occurrence wins
        upsert_rows = list(dedup.values())
        rows_deduped = len(rows) - len(upsert_rows)
        phases["row_builder_ms"] = round((time.perf_counter() - t_row_builder_start) * 1000, 1)
        phases["rows_deduped"] = rows_deduped

        if not upsert_rows:
            phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
            logger.info("usaspending_batch_persist_phases", extra=phases)
            return {
                "table_name": USASPENDING_TABLE_NAME,
                "extract_date": source_context["extract_date"],
                "rows_received": len(rows),
                "rows_written": 0,
            }

        # Collect all columns present across rows
        columns: list[str] = []
        seen: set[str] = set()
        for row_dict in upsert_rows:
            for col_name in row_dict:
                if col_name not in seen:
                    seen.add(col_name)
                    columns.append(col_name)

        # Build temp table name
        suffix = uuid4().hex[:8]
        temp_table_name = f"tmp_usaspending_{suffix}"

        # Build merge SQL
        quoted_columns = ", ".join(_quote_identifier(c) for c in columns)
        projected_columns = ", ".join(_quote_identifier(c) for c in columns)
        quoted_conflict = ", ".join(_quote_identifier(c) for c in USASPENDING_CONFLICT_COLUMNS)

        update_assignments = [
            f'{_quote_identifier(c)} = EXCLUDED.{_quote_identifier(c)}'
            for c in columns
            if c not in USASPENDING_CONFLICT_COLUMNS
            and c not in USASPENDING_INSERT_ONLY_ON_CONFLICT_COLUMNS
        ]

        upsert_sql = (
            f"INSERT INTO {_quote_qualified_identifier(USASPENDING_SCHEMA, USASPENDING_TABLE_NAME)} "
            f"({quoted_columns}) SELECT {projected_columns} "
            f"FROM {_quote_identifier(temp_table_name)} "
            f"ON CONFLICT ({quoted_conflict}) DO UPDATE SET "
            f"{', '.join(update_assignments)}"
        )

        # Build COPY payload
        serialized_rows: list[str] = []
        for row_dict in upsert_rows:
            serialized_rows.append(
                _COPY_DELIMITER.join(
                    _serialize_copy_value(row_dict.get(col_name))
                    for col_name in columns
                )
            )
        copy_payload = f"{_COPY_ROW_DELIMITER.join(serialized_rows)}{_COPY_ROW_DELIMITER}"

        # Phase 2: Acquire connection and execute
        pool = _get_usaspending_connection_pool()
        t_conn_start = time.perf_counter()
        with pool.connection() as connection:
            phases["connection_acquire_ms"] = round((time.perf_counter() - t_conn_start) * 1000, 1)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = '600s'")

                    # Create temp staging table
                    t_temp = time.perf_counter()
                    cursor.execute(
                        f"CREATE TEMP TABLE {_quote_identifier(temp_table_name)} "
                        f"(LIKE {_quote_qualified_identifier(USASPENDING_SCHEMA, USASPENDING_TABLE_NAME)} INCLUDING DEFAULTS) "
                        "ON COMMIT DROP"
                    )
                    phases["temp_table_create_ms"] = round((time.perf_counter() - t_temp) * 1000, 1)

                    # COPY into temp table
                    t_copy = time.perf_counter()
                    copy_sql = (
                        f"COPY {_quote_identifier(temp_table_name)} ({quoted_columns}) "
                        "FROM STDIN WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')"
                    )
                    with cursor.copy(copy_sql) as copy:
                        copy.write(copy_payload)
                    phases["copy_ms"] = round((time.perf_counter() - t_copy) * 1000, 1)

                    # Merge to live table
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
                        with connection.cursor() as cleanup_cursor:
                            cleanup_cursor.execute(
                                f"DROP TABLE IF EXISTS {_quote_identifier(temp_table_name)}"
                            )
                    except Exception:
                        pass
                raise

        phases["rows_written"] = len(upsert_rows)
        phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
        logger.info("usaspending_batch_persist_phases", extra=phases)

        return {
            "table_name": USASPENDING_TABLE_NAME,
            "extract_date": source_context["extract_date"],
            "rows_received": len(rows),
            "rows_written": len(upsert_rows),
        }
    except Exception:
        phases["error"] = True
        phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
        logger.info("usaspending_batch_persist_phases", extra=phases)
        raise
