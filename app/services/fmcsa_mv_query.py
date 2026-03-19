"""FMCSA Carrier MV Query — search and convenience queries against materialized views."""
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


def _safe_carrier_conditions(alias: str = "cm") -> list[str]:
    """Standard safe carrier filter: no alerts, all percentiles below 50, no crashes."""
    return [
        f"{alias}.unsafe_driving_basic_alert IS NOT TRUE",
        f"{alias}.hours_of_service_basic_alert IS NOT TRUE",
        f"{alias}.vehicle_maintenance_basic_alert IS NOT TRUE",
        f"{alias}.driver_fitness_basic_alert IS NOT TRUE",
        f"{alias}.controlled_substances_alcohol_basic_alert IS NOT TRUE",
        f"COALESCE({alias}.unsafe_driving_percentile, 0) < 50",
        f"COALESCE({alias}.hours_of_service_percentile, 0) < 50",
        f"COALESCE({alias}.vehicle_maintenance_percentile, 0) < 50",
        f"COALESCE({alias}.driver_fitness_percentile, 0) < 50",
        f"COALESCE({alias}.controlled_substances_alcohol_percentile, 0) < 50",
        f"{alias}.crash_count_12mo = 0",
    ]


# ---------------------------------------------------------------------------
# Filter builder helpers
# ---------------------------------------------------------------------------

_ALERT_COLUMNS = [
    "unsafe_driving_basic_alert",
    "hours_of_service_basic_alert",
    "vehicle_maintenance_basic_alert",
    "driver_fitness_basic_alert",
    "controlled_substances_alcohol_basic_alert",
]


def _build_carrier_where(
    filters: dict[str, Any],
    alias: str = "cm",
) -> tuple[str, list[Any]]:
    """Build WHERE clause for carrier master queries."""
    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("state"):
        conditions.append(f"{alias}.physical_state = %s")
        params.append(filters["state"])

    if filters.get("city"):
        conditions.append(f"{alias}.physical_city ILIKE %s")
        params.append(f"%{filters['city']}%")

    if filters.get("min_power_units") is not None:
        conditions.append(f"{alias}.power_unit_count >= %s")
        params.append(filters["min_power_units"])

    if filters.get("max_power_units") is not None:
        conditions.append(f"{alias}.power_unit_count <= %s")
        params.append(filters["max_power_units"])

    if filters.get("max_unsafe_driving") is not None:
        conditions.append(f"{alias}.unsafe_driving_percentile <= %s")
        params.append(filters["max_unsafe_driving"])

    if filters.get("max_hos") is not None:
        conditions.append(f"{alias}.hours_of_service_percentile <= %s")
        params.append(filters["max_hos"])

    if filters.get("max_vehicle_maintenance") is not None:
        conditions.append(f"{alias}.vehicle_maintenance_percentile <= %s")
        params.append(filters["max_vehicle_maintenance"])

    if filters.get("max_driver_fitness") is not None:
        conditions.append(f"{alias}.driver_fitness_percentile <= %s")
        params.append(filters["max_driver_fitness"])

    if filters.get("max_controlled_substances") is not None:
        conditions.append(f"{alias}.controlled_substances_alcohol_percentile <= %s")
        params.append(filters["max_controlled_substances"])

    if filters.get("has_alerts") is True:
        or_parts = " OR ".join(f"{alias}.{col} = TRUE" for col in _ALERT_COLUMNS)
        conditions.append(f"({or_parts})")
    elif filters.get("has_alerts") is False:
        conditions.extend(f"{alias}.{col} IS NOT TRUE" for col in _ALERT_COLUMNS)

    if filters.get("has_crashes") is True:
        conditions.append(f"{alias}.crash_count_12mo > 0")
    elif filters.get("has_crashes") is False:
        conditions.append(f"{alias}.crash_count_12mo = 0")

    if filters.get("has_email") is True:
        conditions.append(f"{alias}.email_address IS NOT NULL AND {alias}.email_address != ''")
    elif filters.get("has_email") is False:
        conditions.append(f"({alias}.email_address IS NULL OR {alias}.email_address = '')")

    if filters.get("has_phone") is True:
        conditions.append(f"{alias}.telephone IS NOT NULL AND {alias}.telephone != ''")
    elif filters.get("has_phone") is False:
        conditions.append(f"({alias}.telephone IS NULL OR {alias}.telephone = '')")

    if filters.get("safety_rating_code"):
        conditions.append(f"{alias}.safety_rating_code = %s")
        params.append(filters["safety_rating_code"])

    if filters.get("legal_name_contains"):
        conditions.append(f"{alias}.legal_name ILIKE %s")
        params.append(f"%{filters['legal_name_contains']}%")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    return where_clause, params


_SORT_OPTIONS = {
    "fleet_size": "cm.power_unit_count DESC NULLS LAST, cm.dot_number",
    "state": "cm.physical_state ASC, cm.power_unit_count DESC NULLS LAST",
    "safety": "cm.unsafe_driving_percentile ASC NULLS LAST, cm.dot_number",
}


# ---------------------------------------------------------------------------
# 1b: search_carriers
# ---------------------------------------------------------------------------

def search_carriers(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    where_clause, params = _build_carrier_where(filters)
    sort_by = filters.get("sort_by", "fleet_size")
    order_clause = _SORT_OPTIONS.get(sort_by, _SORT_OPTIONS["fleet_size"])

    sql = f"""
        SELECT cm.*, COUNT(*) OVER() AS total_matched
        FROM entities.mv_fmcsa_carrier_master cm
        {where_clause}
        ORDER BY {order_clause}
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


# ---------------------------------------------------------------------------
# 1c: search_insurance_cancellations
# ---------------------------------------------------------------------------

def search_insurance_cancellations(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("state"):
        conditions.append("cm.physical_state = %s")
        params.append(filters["state"])

    if filters.get("cancel_date_from"):
        conditions.append("ic.cancel_effective_date >= %s::DATE")
        params.append(filters["cancel_date_from"])

    if filters.get("cancel_date_to"):
        conditions.append("ic.cancel_effective_date <= %s::DATE")
        params.append(filters["cancel_date_to"])

    if filters.get("insurance_type"):
        conditions.append("ic.insurance_type_indicator = %s")
        params.append(filters["insurance_type"])

    if filters.get("min_power_units") is not None:
        conditions.append("cm.power_unit_count >= %s")
        params.append(filters["min_power_units"])

    if filters.get("max_power_units") is not None:
        conditions.append("cm.power_unit_count <= %s")
        params.append(filters["max_power_units"])

    if filters.get("safe_only") is True:
        conditions.extend(_safe_carrier_conditions("cm"))

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            cm.dot_number, cm.legal_name, cm.dba_name, cm.physical_state, cm.physical_city,
            cm.power_unit_count, cm.driver_total, cm.telephone, cm.email_address,
            cm.unsafe_driving_percentile, cm.hours_of_service_percentile,
            cm.vehicle_maintenance_percentile, cm.crash_count_12mo,
            ic.cancel_effective_date, ic.insurance_type_indicator, ic.insurance_type_description,
            ic.insurance_company_name, ic.policy_number, ic.effective_date,
            ic.bipd_underlying_limit_amount_thousands_usd, ic.bipd_max_coverage_amount_thousands_usd,
            COUNT(*) OVER() AS total_matched
        FROM entities.mv_fmcsa_insurance_cancellations ic
        JOIN entities.mv_fmcsa_carrier_master cm
            ON LTRIM(ic.usdot_number, '0') = cm.dot_number
        {where_clause}
        ORDER BY ic.cancel_effective_date DESC, cm.dot_number
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


# ---------------------------------------------------------------------------
# 1d: search_new_authority
# ---------------------------------------------------------------------------

def search_new_authority(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("state"):
        conditions.append("cm.physical_state = %s")
        params.append(filters["state"])

    if filters.get("served_date_from"):
        conditions.append("ag.original_authority_action_served_date >= %s::DATE")
        params.append(filters["served_date_from"])

    if filters.get("served_date_to"):
        conditions.append("ag.original_authority_action_served_date <= %s::DATE")
        params.append(filters["served_date_to"])

    if filters.get("authority_type"):
        conditions.append("ag.operating_authority_type = %s")
        params.append(filters["authority_type"])

    if filters.get("min_power_units") is not None:
        conditions.append("cm.power_unit_count >= %s")
        params.append(filters["min_power_units"])

    if filters.get("max_power_units") is not None:
        conditions.append("cm.power_unit_count <= %s")
        params.append(filters["max_power_units"])

    if filters.get("safe_only") is True:
        conditions.extend(_safe_carrier_conditions("cm"))

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            cm.dot_number, cm.legal_name, cm.dba_name, cm.physical_state, cm.physical_city,
            cm.power_unit_count, cm.driver_total, cm.telephone, cm.email_address,
            cm.unsafe_driving_percentile, cm.hours_of_service_percentile,
            cm.vehicle_maintenance_percentile, cm.crash_count_12mo,
            ag.operating_authority_type, ag.original_authority_action_served_date,
            ag.final_authority_decision_date, ag.docket_number,
            COUNT(*) OVER() AS total_matched
        FROM entities.mv_fmcsa_authority_grants ag
        JOIN entities.mv_fmcsa_carrier_master cm
            ON LTRIM(ag.usdot_number, '0') = cm.dot_number
        {where_clause}
        ORDER BY ag.original_authority_action_served_date DESC, cm.dot_number
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


# ---------------------------------------------------------------------------
# 1e: Convenience queries
# ---------------------------------------------------------------------------

def search_safe_losing_coverage(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Safe carriers losing insurance coverage (last 30 days default)."""
    inner_filters: dict[str, Any] = {
        "safe_only": True,
        "cancel_date_from": filters.get("cancel_date_from") or "CURRENT_DATE - INTERVAL '30 days'",
    }
    # Use SQL expression for default date
    if not filters.get("cancel_date_from"):
        # We need to handle this differently — use a raw SQL default
        inner_filters.pop("cancel_date_from")

    for key in ("state", "cancel_date_from", "cancel_date_to", "min_power_units", "max_power_units"):
        if filters.get(key) is not None:
            inner_filters[key] = filters[key]

    # If no cancel_date_from provided, build the query with a SQL default
    if "cancel_date_from" not in inner_filters:
        return _search_safe_losing_coverage_with_default(
            filters=inner_filters, limit=limit, offset=offset,
        )

    inner_filters["safe_only"] = True
    return search_insurance_cancellations(filters=inner_filters, limit=limit, offset=offset)


def _search_safe_losing_coverage_with_default(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Internal: safe carriers losing coverage with SQL-computed default date."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = [
        "ic.cancel_effective_date >= CURRENT_DATE - INTERVAL '30 days'",
    ]
    conditions.extend(_safe_carrier_conditions("cm"))
    params: list[Any] = []

    if filters.get("state"):
        conditions.append("cm.physical_state = %s")
        params.append(filters["state"])

    if filters.get("cancel_date_to"):
        conditions.append("ic.cancel_effective_date <= %s::DATE")
        params.append(filters["cancel_date_to"])

    if filters.get("min_power_units") is not None:
        conditions.append("cm.power_unit_count >= %s")
        params.append(filters["min_power_units"])

    if filters.get("max_power_units") is not None:
        conditions.append("cm.power_unit_count <= %s")
        params.append(filters["max_power_units"])

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            cm.dot_number, cm.legal_name, cm.dba_name, cm.physical_state, cm.physical_city,
            cm.power_unit_count, cm.driver_total, cm.telephone, cm.email_address,
            cm.unsafe_driving_percentile, cm.hours_of_service_percentile,
            cm.vehicle_maintenance_percentile, cm.crash_count_12mo,
            ic.cancel_effective_date, ic.insurance_type_indicator, ic.insurance_type_description,
            ic.insurance_company_name, ic.policy_number, ic.effective_date,
            ic.bipd_underlying_limit_amount_thousands_usd, ic.bipd_max_coverage_amount_thousands_usd,
            COUNT(*) OVER() AS total_matched
        FROM entities.mv_fmcsa_insurance_cancellations ic
        JOIN entities.mv_fmcsa_carrier_master cm
            ON LTRIM(ic.usdot_number, '0') = cm.dot_number
        {where_clause}
        ORDER BY ic.cancel_effective_date DESC, cm.dot_number
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


def search_safe_new_entrants(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Safe carriers with new authority grants (last 60 days default)."""
    if filters.get("served_date_from"):
        inner_filters: dict[str, Any] = {"safe_only": True}
        for key in ("state", "served_date_from", "served_date_to", "min_power_units", "max_power_units"):
            if filters.get(key) is not None:
                inner_filters[key] = filters[key]
        inner_filters["safe_only"] = True
        return search_new_authority(filters=inner_filters, limit=limit, offset=offset)

    return _search_safe_new_entrants_with_default(filters=filters, limit=limit, offset=offset)


def _search_safe_new_entrants_with_default(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Internal: safe new entrants with SQL-computed default date."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = [
        "ag.original_authority_action_served_date >= CURRENT_DATE - INTERVAL '60 days'",
    ]
    conditions.extend(_safe_carrier_conditions("cm"))
    params: list[Any] = []

    if filters.get("state"):
        conditions.append("cm.physical_state = %s")
        params.append(filters["state"])

    if filters.get("served_date_to"):
        conditions.append("ag.original_authority_action_served_date <= %s::DATE")
        params.append(filters["served_date_to"])

    if filters.get("min_power_units") is not None:
        conditions.append("cm.power_unit_count >= %s")
        params.append(filters["min_power_units"])

    if filters.get("max_power_units") is not None:
        conditions.append("cm.power_unit_count <= %s")
        params.append(filters["max_power_units"])

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            cm.dot_number, cm.legal_name, cm.dba_name, cm.physical_state, cm.physical_city,
            cm.power_unit_count, cm.driver_total, cm.telephone, cm.email_address,
            cm.unsafe_driving_percentile, cm.hours_of_service_percentile,
            cm.vehicle_maintenance_percentile, cm.crash_count_12mo,
            ag.operating_authority_type, ag.original_authority_action_served_date,
            ag.final_authority_decision_date, ag.docket_number,
            COUNT(*) OVER() AS total_matched
        FROM entities.mv_fmcsa_authority_grants ag
        JOIN entities.mv_fmcsa_carrier_master cm
            ON LTRIM(ag.usdot_number, '0') = cm.dot_number
        {where_clause}
        ORDER BY ag.original_authority_action_served_date DESC, cm.dot_number
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


def search_safe_mid_market(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    """Safe mid-market carriers (10-50 power units, no alerts, no crashes)."""
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = [
        "cm.power_unit_count BETWEEN 10 AND 50",
    ]
    conditions.extend(_safe_carrier_conditions("cm"))
    params: list[Any] = []

    if filters.get("state"):
        conditions.append("cm.physical_state = %s")
        params.append(filters["state"])

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT cm.*, COUNT(*) OVER() AS total_matched
        FROM entities.mv_fmcsa_carrier_master cm
        {where_clause}
        ORDER BY cm.power_unit_count DESC NULLS LAST, cm.dot_number
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
