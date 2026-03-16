# app/services/sam_gov_common.py — SAM.gov bulk persistence utilities
#
# Follows the proven COPY-based bulk write pattern from fmcsa_daily_diff_common.py,
# adapted for SAM.gov pipe-delimited entity extract files.

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Any, TypedDict
from uuid import uuid4

from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.services.sam_gov_column_map import SAM_GOV_COLUMN_COUNT, SAM_GOV_DB_COLUMN_NAMES

logger = logging.getLogger(__name__)

_sam_gov_pool: ConnectionPool | None = None
_sam_gov_pool_lock = threading.Lock()

SAM_GOV_TABLE_NAME = "sam_gov_entities"
SAM_GOV_SCHEMA = "entities"
SAM_GOV_CONFLICT_COLUMNS = ("extract_date", "unique_entity_id")
SAM_GOV_INSERT_ONLY_ON_CONFLICT_COLUMNS = frozenset({"created_at"})

_SQL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COPY_NULL_TOKEN = r"\N"
_COPY_DELIMITER = "\t"
_COPY_ROW_DELIMITER = "\n"


class SamGovSourceContext(TypedDict):
    extract_date: str       # YYYY-MM-DD
    extract_type: str       # MONTHLY or DAILY
    source_filename: str    # original .dat filename
    source_download_url: str  # download URL


class SamGovExtractRow(TypedDict):
    row_number: int
    raw_line: str           # original pipe-delimited line
    fields: list[str]       # split fields (142 items)


def _get_sam_gov_connection_pool() -> ConnectionPool:
    global _sam_gov_pool
    if _sam_gov_pool is not None:
        return _sam_gov_pool
    with _sam_gov_pool_lock:
        if _sam_gov_pool is not None:
            return _sam_gov_pool
        settings = get_settings()
        _sam_gov_pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=4,
            timeout=30.0,
        )
        return _sam_gov_pool


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


def parse_sam_gov_dat_line(line: str, row_number: int) -> SamGovExtractRow | None:
    """Parse a single pipe-delimited line from a SAM.gov .dat extract file.

    Returns SamGovExtractRow on success, None on validation failure (logged).
    """
    stripped = line.rstrip("\n").rstrip("\r")
    fields = stripped.split("|")

    if len(fields) != SAM_GOV_COLUMN_COUNT:
        logger.warning(
            "sam_gov_parse_field_count_mismatch",
            extra={
                "row_number": row_number,
                "expected_fields": SAM_GOV_COLUMN_COUNT,
                "actual_fields": len(fields),
            },
        )
        return None

    # Verify end-of-record marker
    end_marker = fields[-1].strip()
    if end_marker != "!end":
        logger.warning(
            "sam_gov_parse_missing_end_marker",
            extra={
                "row_number": row_number,
                "last_field": end_marker[:20],
            },
        )
        return None

    return SamGovExtractRow(
        row_number=row_number,
        raw_line=stripped,
        fields=fields,
    )


def build_sam_gov_entity_row(
    row: SamGovExtractRow,
    source_context: SamGovSourceContext,
) -> dict[str, Any]:
    """Map positional fields to snake_case column names and add extract metadata."""
    result: dict[str, Any] = {}

    # Map the 142 positional fields to named columns
    for i, db_col_name in enumerate(SAM_GOV_DB_COLUMN_NAMES):
        raw_value = row["fields"][i]
        # Strip whitespace; convert empty strings to None
        cleaned = raw_value.strip() if raw_value else None
        result[db_col_name] = cleaned if cleaned else None

    # Add extract metadata columns
    result["extract_date"] = source_context["extract_date"]
    result["extract_type"] = source_context["extract_type"]
    # extract_code from column 6 (zero-indexed position 5)
    result["extract_code"] = result.get("sam_extract_code")
    result["source_filename"] = source_context["source_filename"]
    result["source_provider"] = "sam_gov"
    result["source_download_url"] = source_context["source_download_url"]
    result["row_position"] = row["row_number"]
    result["raw_source_row"] = row["raw_line"]

    return result


def upsert_sam_gov_entities(
    *,
    source_context: SamGovSourceContext,
    rows: list[SamGovExtractRow],
) -> dict[str, Any]:
    """Bulk upsert SAM.gov entity rows using the COPY-based staging pattern."""
    t_total_start = time.perf_counter()
    phases: dict[str, Any] = {
        "table_name": SAM_GOV_TABLE_NAME,
        "extract_date": source_context["extract_date"],
        "rows_received": len(rows),
        "rows_written": 0,
        "error": False,
    }

    try:
        # Phase 1: Build typed rows
        t_row_builder_start = time.perf_counter()
        upsert_rows: list[dict[str, Any]] = []
        for row in rows:
            typed_row = build_sam_gov_entity_row(row, source_context)
            upsert_rows.append(typed_row)
        phases["row_builder_ms"] = round((time.perf_counter() - t_row_builder_start) * 1000, 1)

        if not upsert_rows:
            phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
            logger.info("sam_gov_batch_persist_phases", extra=phases)
            return {
                "table_name": SAM_GOV_TABLE_NAME,
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
        temp_table_name = f"tmp_sam_gov_{suffix}"

        # Build merge SQL
        quoted_columns = ", ".join(_quote_identifier(c) for c in columns)
        projected_columns = ", ".join(_quote_identifier(c) for c in columns)
        quoted_conflict = ", ".join(_quote_identifier(c) for c in SAM_GOV_CONFLICT_COLUMNS)

        update_assignments = [
            f'{_quote_identifier(c)} = EXCLUDED.{_quote_identifier(c)}'
            for c in columns
            if c not in SAM_GOV_CONFLICT_COLUMNS
            and c not in SAM_GOV_INSERT_ONLY_ON_CONFLICT_COLUMNS
        ]

        upsert_sql = (
            f"INSERT INTO {_quote_qualified_identifier(SAM_GOV_SCHEMA, SAM_GOV_TABLE_NAME)} "
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
        pool = _get_sam_gov_connection_pool()
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
                        f"(LIKE {_quote_qualified_identifier(SAM_GOV_SCHEMA, SAM_GOV_TABLE_NAME)} INCLUDING DEFAULTS) "
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
        logger.info("sam_gov_batch_persist_phases", extra=phases)

        return {
            "table_name": SAM_GOV_TABLE_NAME,
            "extract_date": source_context["extract_date"],
            "rows_received": len(rows),
            "rows_written": len(upsert_rows),
        }
    except Exception:
        phases["error"] = True
        phases["total_ms"] = round((time.perf_counter() - t_total_start) * 1000, 1)
        logger.info("sam_gov_batch_persist_phases", extra=phases)
        raise
