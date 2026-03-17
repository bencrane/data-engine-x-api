"""FMCSA Safety Risk Search — census + safety percentiles + crash count join."""
from __future__ import annotations

import logging
import threading
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.services.fmcsa_carrier_query import CENSUS_CURATED_COLUMNS

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

SAFETY_RETURN_COLUMNS = [
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
    "inspection_total",
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
            max_size=4,
            timeout=30.0,
        )
        return _pool


def query_fmcsa_safety_risk(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    # Census filters
    if filters.get("state"):
        conditions.append("census.physical_state = %s")
        params.append(filters["state"])

    if filters.get("min_power_units") is not None:
        conditions.append("census.power_unit_count >= %s")
        params.append(filters["min_power_units"])

    # Safety percentile filters
    if filters.get("min_unsafe_driving_percentile") is not None:
        conditions.append("safety.unsafe_driving_percentile >= %s")
        params.append(filters["min_unsafe_driving_percentile"])

    if filters.get("min_hos_percentile") is not None:
        conditions.append("safety.hours_of_service_percentile >= %s")
        params.append(filters["min_hos_percentile"])

    if filters.get("min_vehicle_maintenance_percentile") is not None:
        conditions.append("safety.vehicle_maintenance_percentile >= %s")
        params.append(filters["min_vehicle_maintenance_percentile"])

    if filters.get("min_driver_fitness_percentile") is not None:
        conditions.append("safety.driver_fitness_percentile >= %s")
        params.append(filters["min_driver_fitness_percentile"])

    if filters.get("min_controlled_substances_percentile") is not None:
        conditions.append("safety.controlled_substances_alcohol_percentile >= %s")
        params.append(filters["min_controlled_substances_percentile"])

    # Safety alert filters
    if filters.get("has_alert_unsafe_driving"):
        conditions.append("safety.unsafe_driving_basic_alert = TRUE")

    if filters.get("has_alert_hos"):
        conditions.append("safety.hours_of_service_basic_alert = TRUE")

    if filters.get("has_alert_vehicle_maintenance"):
        conditions.append("safety.vehicle_maintenance_basic_alert = TRUE")

    if filters.get("has_alert_driver_fitness"):
        conditions.append("safety.driver_fitness_basic_alert = TRUE")

    if filters.get("has_alert_controlled_substances"):
        conditions.append("safety.controlled_substances_alcohol_basic_alert = TRUE")

    # Crash count filter
    if filters.get("min_crash_count_12mo") is not None:
        conditions.append("COALESCE(crashes.crash_count_12mo, 0) >= %s")
        params.append(filters["min_crash_count_12mo"])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    census_cols = ", ".join(f"census.{c}" for c in CENSUS_CURATED_COLUMNS)
    safety_cols = ", ".join(f"safety.{c}" for c in SAFETY_RETURN_COLUMNS)

    sql = f"""
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
        ),
        crash_counts AS (
            SELECT dot_number, COUNT(*) AS crash_count_12mo
            FROM entities.commercial_vehicle_crashes
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.commercial_vehicle_crashes)
              AND report_date >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY dot_number
        )
        SELECT {census_cols}, {safety_cols},
               COALESCE(crashes.crash_count_12mo, 0) AS crash_count_12mo,
               COUNT(*) OVER() AS total_matched
        FROM latest_census census
        INNER JOIN latest_safety safety ON census.dot_number = safety.dot_number
        LEFT JOIN crash_counts crashes ON census.dot_number = crashes.dot_number
        {where_clause}
        ORDER BY safety.unsafe_driving_percentile DESC NULLS LAST,
                 census.power_unit_count DESC NULLS LAST
        LIMIT %s OFFSET %s
    """
    params.extend([safe_limit, safe_offset])

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    total_matched = 0
    items: list[dict[str, Any]] = []
    for row in rows:
        total_matched = row.pop("total_matched", 0)
        # Coerce Decimal values to float
        for key in list(row.keys()):
            if row[key] is not None and hasattr(row[key], "as_tuple"):
                row[key] = float(row[key])
        items.append(row)

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }
