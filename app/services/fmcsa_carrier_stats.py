"""FMCSA Carrier Stats — dashboard aggregate statistics."""
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
            max_size=2,
            timeout=30.0,
        )
        return _pool


def get_fmcsa_carrier_stats() -> dict[str, Any]:
    """Return dashboard-level aggregate stats over the latest census snapshot."""
    pool = _get_pool()

    # Census aggregates — single query with multiple expressions
    census_sql = """
        WITH latest AS (
            SELECT DISTINCT ON (dot_number) *
            FROM entities.motor_carrier_census_records
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
            ORDER BY dot_number, row_position
        )
        SELECT
            COUNT(*) AS total_carriers,
            (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records) AS latest_feed_date,
            COUNT(*) FILTER (WHERE authorized_for_hire = TRUE) AS authorized_for_hire_count,
            COUNT(*) FILTER (WHERE private_only = TRUE) AS private_only_count,
            COUNT(*) FILTER (WHERE exempt_for_hire = TRUE) AS exempt_for_hire_count,
            COUNT(*) FILTER (WHERE private_property = TRUE) AS private_property_count,
            COUNT(*) FILTER (WHERE hazmat_flag = TRUE) AS hazmat_carriers,
            COUNT(*) FILTER (WHERE passenger_carrier_flag = TRUE) AS passenger_carriers,
            COUNT(*) FILTER (WHERE power_unit_count BETWEEN 1 AND 5) AS fleet_1_5,
            COUNT(*) FILTER (WHERE power_unit_count BETWEEN 6 AND 25) AS fleet_6_25,
            COUNT(*) FILTER (WHERE power_unit_count BETWEEN 26 AND 100) AS fleet_26_100,
            COUNT(*) FILTER (WHERE power_unit_count > 100) AS fleet_101_plus
        FROM latest
    """

    by_state_sql = """
        WITH latest AS (
            SELECT DISTINCT ON (dot_number) physical_state
            FROM entities.motor_carrier_census_records
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
            ORDER BY dot_number, row_position
        )
        SELECT physical_state AS state, COUNT(*) AS count
        FROM latest
        WHERE physical_state IS NOT NULL
        GROUP BY physical_state
        ORDER BY count DESC
        LIMIT 20
    """

    # Safety alert counts
    safety_sql = """
        WITH latest_safety AS (
            SELECT DISTINCT ON (dot_number) *
            FROM entities.carrier_safety_basic_percentiles
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_safety_basic_percentiles)
            ORDER BY dot_number, row_position
        )
        SELECT
            COUNT(*) FILTER (WHERE unsafe_driving_basic_alert = TRUE) AS carriers_with_unsafe_driving_alert,
            COUNT(*) FILTER (WHERE hours_of_service_basic_alert = TRUE) AS carriers_with_hos_alert,
            COUNT(*) FILTER (WHERE vehicle_maintenance_basic_alert = TRUE) AS carriers_with_vehicle_maintenance_alert,
            COUNT(*) FILTER (WHERE driver_fitness_basic_alert = TRUE) AS carriers_with_driver_fitness_alert,
            COUNT(*) FILTER (WHERE controlled_substances_alcohol_basic_alert = TRUE) AS carriers_with_controlled_substances_alert
        FROM latest_safety
    """

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(census_sql)
            census_stats = dict(cur.fetchone())

            cur.execute(by_state_sql)
            by_state = [dict(r) for r in cur.fetchall()]

            cur.execute(safety_sql)
            safety_stats = dict(cur.fetchone())

    latest_feed_date = census_stats.get("latest_feed_date")

    return {
        "total_carriers": census_stats["total_carriers"],
        "latest_feed_date": str(latest_feed_date) if latest_feed_date else None,
        "by_state": by_state,
        "by_fleet_size": [
            {"bucket": "1-5", "count": census_stats["fleet_1_5"]},
            {"bucket": "6-25", "count": census_stats["fleet_6_25"]},
            {"bucket": "26-100", "count": census_stats["fleet_26_100"]},
            {"bucket": "101+", "count": census_stats["fleet_101_plus"]},
        ],
        "by_classification": {
            "authorized_for_hire": census_stats["authorized_for_hire_count"],
            "private_only": census_stats["private_only_count"],
            "exempt_for_hire": census_stats["exempt_for_hire_count"],
            "private_property": census_stats["private_property_count"],
        },
        "hazmat_carriers": census_stats["hazmat_carriers"],
        "passenger_carriers": census_stats["passenger_carriers"],
        "carriers_with_unsafe_driving_alert": safety_stats["carriers_with_unsafe_driving_alert"],
        "carriers_with_hos_alert": safety_stats["carriers_with_hos_alert"],
        "carriers_with_vehicle_maintenance_alert": safety_stats["carriers_with_vehicle_maintenance_alert"],
        "carriers_with_driver_fitness_alert": safety_stats["carriers_with_driver_fitness_alert"],
        "carriers_with_controlled_substances_alert": safety_stats["carriers_with_controlled_substances_alert"],
    }
