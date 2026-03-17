"""FMCSA Crash History — query service with latest-snapshot filtering."""
from __future__ import annotations

import logging
import threading
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

CRASH_RETURN_COLUMNS = [
    "crash_id",
    "dot_number",
    "report_date",
    "state",
    "city",
    "location",
    "fatalities",
    "injuries",
    "tow_away",
    "hazmat_released",
    "truck_bus_indicator",
    "crash_carrier_name",
    "crash_carrier_state",
    "vehicles_in_accident",
    "weather_condition_id",
    "light_condition_id",
    "road_surface_condition_id",
    "feed_date",
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
            max_size=3,
            timeout=30.0,
        )
        return _pool


def query_fmcsa_crashes(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("dot_number"):
        conditions.append("dot_number = %s")
        params.append(filters["dot_number"])

    if filters.get("state"):
        conditions.append("state = %s")
        params.append(filters["state"])

    if filters.get("report_date_from"):
        conditions.append("report_date >= %s::DATE")
        params.append(filters["report_date_from"])

    if filters.get("report_date_to"):
        conditions.append("report_date <= %s::DATE")
        params.append(filters["report_date_to"])

    if filters.get("min_fatalities") is not None:
        conditions.append("fatalities >= %s")
        params.append(filters["min_fatalities"])

    if filters.get("min_injuries") is not None:
        conditions.append("injuries >= %s")
        params.append(filters["min_injuries"])

    if filters.get("hazmat_released"):
        conditions.append("hazmat_released = TRUE")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    columns = ", ".join(CRASH_RETURN_COLUMNS)

    sql = f"""
        WITH latest AS (
            SELECT *
            FROM entities.commercial_vehicle_crashes
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.commercial_vehicle_crashes)
        )
        SELECT {columns}, COUNT(*) OVER() AS total_matched
        FROM latest
        {where_clause}
        ORDER BY report_date DESC NULLS LAST, crash_id
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
        items.append(row)

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }
