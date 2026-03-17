"""FMCSA Carrier Directory — query service with latest-snapshot filtering."""
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

CENSUS_CURATED_COLUMNS = [
    "dot_number",
    "legal_name",
    "dba_name",
    "carrier_operation_code",
    "physical_street",
    "physical_city",
    "physical_state",
    "physical_zip",
    "telephone",
    "email_address",
    "power_unit_count",
    "driver_total",
    "mcs150_date",
    "mcs150_mileage",
    "mcs150_mileage_year",
    "hazmat_flag",
    "passenger_carrier_flag",
    "authorized_for_hire",
    "private_only",
    "exempt_for_hire",
    "private_property",
    "fleet_size_code",
    "safety_rating_code",
    "safety_rating_date",
    "feed_date",
]

CENSUS_DETAIL_EXTRA_COLUMNS = [
    "fax",
    "mailing_street",
    "mailing_city",
    "mailing_state",
    "mailing_zip",
    "company_officer_1",
    "company_officer_2",
    "add_date",
    "recent_mileage",
    "recent_mileage_year",
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


def _col(name: str, alias: str | None) -> str:
    """Qualify a column name with a table alias if provided."""
    return f"{alias}.{name}" if alias else name


def _build_carrier_where(
    filters: dict[str, Any],
    table_alias: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Build WHERE conditions for carrier census queries.

    Returns (conditions, params) — the caller assembles the WHERE clause
    so it can merge conditions from multiple helpers.

    When *table_alias* is provided, every column reference is qualified
    (e.g. ``census.physical_state``).  When ``None``, columns are bare.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("state"):
        conditions.append(f"{_col('physical_state', table_alias)} = %s")
        params.append(filters["state"])

    if filters.get("min_power_units") is not None:
        conditions.append(f"{_col('power_unit_count', table_alias)} >= %s")
        params.append(filters["min_power_units"])

    if filters.get("max_power_units") is not None:
        conditions.append(f"{_col('power_unit_count', table_alias)} <= %s")
        params.append(filters["max_power_units"])

    if filters.get("carrier_operation"):
        conditions.append(f"{_col('carrier_operation_code', table_alias)} = %s")
        params.append(filters["carrier_operation"])

    if filters.get("authorized_for_hire"):
        conditions.append(f"{_col('authorized_for_hire', table_alias)} = TRUE")

    if filters.get("private_only"):
        conditions.append(f"{_col('private_only', table_alias)} = TRUE")

    if filters.get("exempt_for_hire"):
        conditions.append(f"{_col('exempt_for_hire', table_alias)} = TRUE")

    if filters.get("private_property"):
        conditions.append(f"{_col('private_property', table_alias)} = TRUE")

    if filters.get("hazmat_flag"):
        conditions.append(f"{_col('hazmat_flag', table_alias)} = TRUE")

    if filters.get("passenger_carrier_flag"):
        conditions.append(f"{_col('passenger_carrier_flag', table_alias)} = TRUE")

    if filters.get("mcs150_date_from"):
        conditions.append(f"{_col('mcs150_date', table_alias)} >= %s::DATE")
        params.append(filters["mcs150_date_from"])

    if filters.get("mcs150_date_to"):
        conditions.append(f"{_col('mcs150_date', table_alias)} <= %s::DATE")
        params.append(filters["mcs150_date_to"])

    if filters.get("legal_name_contains"):
        conditions.append(f"{_col('legal_name', table_alias)} ILIKE %s")
        params.append(f"%{filters['legal_name_contains']}%")

    if filters.get("dot_number"):
        conditions.append(f"{_col('dot_number', table_alias)} = %s")
        params.append(filters["dot_number"])

    if filters.get("min_drivers") is not None:
        conditions.append(f"{_col('driver_total', table_alias)} >= %s")
        params.append(filters["min_drivers"])

    if filters.get("max_drivers") is not None:
        conditions.append(f"{_col('driver_total', table_alias)} <= %s")
        params.append(filters["max_drivers"])

    return conditions, params


def _build_safety_where(
    filters: dict[str, Any],
    table_alias: str | None = None,
) -> tuple[list[str], list[Any]]:
    """Build WHERE conditions for safety percentile filters.

    When *table_alias* is provided, every column reference is qualified.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("min_unsafe_driving_percentile") is not None:
        conditions.append(f"{_col('unsafe_driving_percentile', table_alias)} >= %s")
        params.append(filters["min_unsafe_driving_percentile"])

    if filters.get("min_hours_of_service_percentile") is not None:
        conditions.append(f"{_col('hours_of_service_percentile', table_alias)} >= %s")
        params.append(filters["min_hours_of_service_percentile"])

    if filters.get("min_vehicle_maintenance_percentile") is not None:
        conditions.append(f"{_col('vehicle_maintenance_percentile', table_alias)} >= %s")
        params.append(filters["min_vehicle_maintenance_percentile"])

    if filters.get("has_alert_unsafe_driving"):
        conditions.append(f"{_col('unsafe_driving_basic_alert', table_alias)} = TRUE")

    if filters.get("has_alert_vehicle_maintenance"):
        conditions.append(f"{_col('vehicle_maintenance_basic_alert', table_alias)} = TRUE")

    if filters.get("has_alert_driver_fitness"):
        conditions.append(f"{_col('driver_fitness_basic_alert', table_alias)} = TRUE")

    return conditions, params


def _conditions_to_where(conditions: list[str]) -> str:
    """Join a list of conditions into a WHERE clause (or empty string)."""
    if not conditions:
        return ""
    return "WHERE " + " AND ".join(conditions)


def query_fmcsa_carriers(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions, params = _build_carrier_where(filters)
    where_clause = _conditions_to_where(conditions)

    columns = ", ".join(CENSUS_CURATED_COLUMNS)

    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (dot_number) *
            FROM entities.motor_carrier_census_records
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
            ORDER BY dot_number, row_position
        )
        SELECT {columns}, COUNT(*) OVER() AS total_matched
        FROM latest
        {where_clause}
        ORDER BY power_unit_count DESC NULLS LAST, dot_number
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
