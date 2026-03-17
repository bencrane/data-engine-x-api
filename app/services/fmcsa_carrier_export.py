"""FMCSA Carrier CSV Export — streaming cursor with safety percentile LEFT JOIN."""
from __future__ import annotations

import csv
import io
import logging
import threading
from typing import Any, Iterator

from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.services.fmcsa_carrier_query import (
    CENSUS_CURATED_COLUMNS,
    _build_carrier_where,
    _build_safety_where,
    _conditions_to_where,
)

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

SAFETY_EXPORT_COLUMNS = [
    "unsafe_driving_percentile",
    "hours_of_service_percentile",
    "driver_fitness_percentile",
    "controlled_substances_alcohol_percentile",
    "vehicle_maintenance_percentile",
    "unsafe_driving_basic_alert",
    "hours_of_service_basic_alert",
    "driver_fitness_basic_alert",
    "controlled_substances_alcohol_basic_alert",
    "vehicle_maintenance_basic_alert",
]


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is not None:
            return _pool
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=2,
            timeout=30.0,
        )
        return _pool


def stream_fmcsa_carriers_csv(
    *,
    filters: dict[str, Any],
    max_rows: int = 100_000,
) -> Iterator[str]:
    """Yield CSV lines for all matching FMCSA carrier rows.

    Uses a server-side cursor to avoid loading all rows into memory.
    Raises ValueError if the result set exceeds max_rows.
    """
    census_conditions, census_params = _build_carrier_where(filters, table_alias="census")
    safety_conditions, safety_params = _build_safety_where(filters, table_alias="safety")

    all_conditions = census_conditions + safety_conditions
    all_params = census_params + safety_params

    where_clause = _conditions_to_where(all_conditions)

    # Prefix columns with aliases for the joined query
    census_cols = ", ".join(f"census.{c}" for c in CENSUS_CURATED_COLUMNS)
    safety_cols = ", ".join(f"safety.{c}" for c in SAFETY_EXPORT_COLUMNS)

    base_cte = """
        WITH latest_census AS (
            SELECT DISTINCT ON (dot_number) *
            FROM entities.motor_carrier_census_records
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
            ORDER BY dot_number, row_position
        ),
        latest_safety AS (
            SELECT DISTINCT ON (dot_number) *
            FROM entities.carrier_safety_basic_percentiles
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_safety_basic_percentiles)
            ORDER BY dot_number, row_position
        )
    """

    # Count check first
    count_sql = f"""
        {base_cte}
        SELECT COUNT(*)
        FROM latest_census census
        LEFT JOIN latest_safety safety ON census.dot_number = safety.dot_number
        {where_clause}
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, all_params)
            total = cur.fetchone()[0]

    if total > max_rows:
        raise ValueError(
            f"Export would return {total} rows, exceeding the limit of {max_rows}. "
            "Add filters to narrow results."
        )

    # Stream results with server-side cursor
    data_sql = f"""
        {base_cte}
        SELECT {census_cols}, {safety_cols}
        FROM latest_census census
        LEFT JOIN latest_safety safety ON census.dot_number = safety.dot_number
        {where_clause}
        ORDER BY census.power_unit_count DESC NULLS LAST, census.dot_number
    """

    all_columns = CENSUS_CURATED_COLUMNS + SAFETY_EXPORT_COLUMNS

    with pool.connection() as conn:
        with conn.cursor(name="fmcsa_csv_export_cursor") as cur:
            cur.itersize = 5000
            cur.execute(data_sql, all_params)

            # Yield header row
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(all_columns)
            yield buf.getvalue()

            # Yield data rows in chunks
            while True:
                rows = cur.fetchmany(5000)
                if not rows:
                    break
                for row in rows:
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(row)
                    yield buf.getvalue()
