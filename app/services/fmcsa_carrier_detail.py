"""FMCSA Carrier Detail — multi-table profile aggregated in Python."""
from __future__ import annotations

import logging
import threading
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings
from app.services.fmcsa_carrier_query import (
    CENSUS_CURATED_COLUMNS,
    CENSUS_DETAIL_EXTRA_COLUMNS,
)

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
            max_size=3,
            timeout=30.0,
        )
        return _pool


def get_fmcsa_carrier_detail(*, dot_number: str) -> dict[str, Any] | None:
    """Build a complete carrier profile by querying multiple tables."""
    pool = _get_pool()

    # 1. Census record
    census_columns = ", ".join(CENSUS_CURATED_COLUMNS + CENSUS_DETAIL_EXTRA_COLUMNS)
    census_sql = f"""
        SELECT DISTINCT ON (dot_number) {census_columns}
        FROM entities.motor_carrier_census_records
        WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
          AND dot_number = %s
        ORDER BY dot_number, row_position
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(census_sql, [dot_number])
            census = cur.fetchone()

    if census is None:
        return None

    census = dict(census)

    # 2. Safety percentiles
    safety_sql = """
        SELECT DISTINCT ON (dot_number)
            unsafe_driving_percentile, unsafe_driving_measure,
            unsafe_driving_roadside_alert, unsafe_driving_acute_critical, unsafe_driving_basic_alert,
            hours_of_service_percentile, hours_of_service_measure,
            hours_of_service_roadside_alert, hours_of_service_acute_critical, hours_of_service_basic_alert,
            driver_fitness_percentile, driver_fitness_measure,
            driver_fitness_roadside_alert, driver_fitness_acute_critical, driver_fitness_basic_alert,
            controlled_substances_alcohol_percentile, controlled_substances_alcohol_measure,
            controlled_substances_alcohol_roadside_alert, controlled_substances_alcohol_acute_critical,
            controlled_substances_alcohol_basic_alert,
            vehicle_maintenance_percentile, vehicle_maintenance_measure,
            vehicle_maintenance_roadside_alert, vehicle_maintenance_acute_critical,
            vehicle_maintenance_basic_alert,
            inspection_total, driver_inspection_total, vehicle_inspection_total, carrier_segment
        FROM entities.carrier_safety_basic_percentiles
        WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_safety_basic_percentiles)
          AND dot_number = %s
        ORDER BY dot_number, row_position
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(safety_sql, [dot_number])
            safety_row = cur.fetchone()

    safety = dict(safety_row) if safety_row else None
    # Coerce Decimal percentiles/measures to float
    if safety:
        for key in list(safety.keys()):
            if safety[key] is not None and hasattr(safety[key], "as_tuple"):
                safety[key] = float(safety[key])

    # 3. Authority status
    authority_sql = """
        SELECT DISTINCT ON (usdot_number)
            docket_number, common_authority_status, contract_authority_status,
            broker_authority_status, pending_common_authority, pending_contract_authority,
            pending_broker_authority, bipd_required_thousands_usd, bipd_on_file_thousands_usd,
            cargo_required, cargo_on_file
        FROM entities.carrier_registrations
        WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_registrations)
          AND usdot_number = %s
        ORDER BY usdot_number, row_position
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(authority_sql, [dot_number])
            authority_row = cur.fetchone()

    authority = dict(authority_row) if authority_row else None
    docket_number = authority["docket_number"] if authority else None

    # 4. Recent crashes
    crashes_sql = """
        WITH latest_crashes AS (
            SELECT crash_id, report_date, state, city, fatalities, injuries, tow_away, hazmat_released
            FROM entities.commercial_vehicle_crashes
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.commercial_vehicle_crashes)
              AND dot_number = %s
        )
        SELECT *
        FROM latest_crashes
        ORDER BY report_date DESC NULLS LAST, crash_id
        LIMIT 5
    """
    crashes_agg_sql = """
        SELECT
            COUNT(*) AS total_crashes,
            MAX(report_date) AS most_recent_crash_date,
            COALESCE(SUM(fatalities), 0) AS total_fatalities,
            COALESCE(SUM(injuries), 0) AS total_injuries
        FROM entities.commercial_vehicle_crashes
        WHERE feed_date = (SELECT MAX(feed_date) FROM entities.commercial_vehicle_crashes)
          AND dot_number = %s
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(crashes_sql, [dot_number])
            crash_records = [dict(r) for r in cur.fetchall()]

            cur.execute(crashes_agg_sql, [dot_number])
            crash_agg = cur.fetchone()

    crash_agg = dict(crash_agg) if crash_agg else {}
    crashes = {
        "total_crashes": crash_agg.get("total_crashes", 0),
        "most_recent_crash_date": str(crash_agg["most_recent_crash_date"]) if crash_agg.get("most_recent_crash_date") else None,
        "total_fatalities": crash_agg.get("total_fatalities", 0),
        "total_injuries": crash_agg.get("total_injuries", 0),
        "records": crash_records,
    }

    # 5. Insurance status
    insurance: list[dict[str, Any]] = []
    if docket_number:
        insurance_sql = """
            SELECT insurance_type_code, insurance_type_description,
                   bipd_maximum_dollar_limit_thousands_usd, policy_number,
                   effective_date, insurance_company_name, is_removal_signal
            FROM entities.insurance_policies
            WHERE docket_number = %s
            ORDER BY effective_date DESC NULLS LAST
        """
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(insurance_sql, [docket_number])
                insurance = [dict(r) for r in cur.fetchall()]

    # 6. Out-of-service orders
    oos_sql = """
        SELECT oos_date, oos_reason, status, oos_rescind_date
        FROM entities.out_of_service_orders
        WHERE feed_date = (SELECT MAX(feed_date) FROM entities.out_of_service_orders)
          AND dot_number = %s
        ORDER BY oos_date DESC NULLS LAST
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(oos_sql, [dot_number])
            oos_orders = [dict(r) for r in cur.fetchall()]

    out_of_service = {
        "total_oos_orders": len(oos_orders),
        "orders": oos_orders,
    }

    return {
        "dot_number": dot_number,
        "census": census,
        "safety": safety,
        "authority": authority,
        "crashes": crashes,
        "insurance": insurance,
        "out_of_service": out_of_service,
    }
