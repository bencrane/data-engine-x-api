"""FMCSA Carrier MV Stats — aggregation queries against materialized views."""
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


def get_carrier_stats(*, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aggregate carrier statistics from materialized views."""
    filters = filters or {}
    pool = _get_pool()

    state_filter = filters.get("state")

    # Build optional state condition for carrier master queries
    cm_where = ""
    cm_params: list[Any] = []
    if state_filter:
        cm_where = "WHERE physical_state = %s"
        cm_params = [state_filter]

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Total carriers
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM entities.mv_fmcsa_carrier_master {cm_where}",
                cm_params,
            )
            total_carriers = cur.fetchone()["cnt"]

            # Carriers by state (top 25)
            cur.execute(
                f"""
                SELECT physical_state AS state, COUNT(*) AS count
                FROM entities.mv_fmcsa_carrier_master
                {cm_where}
                GROUP BY physical_state
                ORDER BY COUNT(*) DESC
                LIMIT 25
                """,
                cm_params,
            )
            carriers_by_state = [dict(r) for r in cur.fetchall()]

            # Carriers with alerts
            alert_or = " OR ".join(
                f"{col} = TRUE" for col in [
                    "unsafe_driving_basic_alert",
                    "hours_of_service_basic_alert",
                    "vehicle_maintenance_basic_alert",
                    "driver_fitness_basic_alert",
                    "controlled_substances_alcohol_basic_alert",
                ]
            )
            alert_where = f"WHERE ({alert_or})"
            if state_filter:
                alert_where += " AND physical_state = %s"
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM entities.mv_fmcsa_carrier_master {alert_where}",
                [state_filter] if state_filter else [],
            )
            carriers_with_alerts = cur.fetchone()["cnt"]

            # Carriers with crashes
            crash_where = "WHERE crash_count_12mo > 0"
            if state_filter:
                crash_where += " AND physical_state = %s"
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM entities.mv_fmcsa_carrier_master {crash_where}",
                [state_filter] if state_filter else [],
            )
            carriers_with_crashes = cur.fetchone()["cnt"]

            # New authority counts (30d, 60d, 90d) — join with carrier_master for state filter
            authority_counts = {}
            for days in (30, 60, 90):
                ag_conditions = [
                    f"ag.original_authority_action_served_date >= CURRENT_DATE - INTERVAL '{days} days'",
                ]
                ag_params: list[Any] = []
                if state_filter:
                    ag_conditions.append("cm.physical_state = %s")
                    ag_params.append(state_filter)
                ag_where = "WHERE " + " AND ".join(ag_conditions)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS cnt
                    FROM entities.mv_fmcsa_authority_grants ag
                    JOIN entities.mv_fmcsa_carrier_master cm
                        ON LTRIM(ag.usdot_number, '0') = cm.dot_number
                    {ag_where}
                    """,
                    ag_params,
                )
                authority_counts[f"new_authority_last_{days}d"] = cur.fetchone()["cnt"]

            # Insurance cancellation counts (30d, 60d, 90d)
            cancel_counts = {}
            for days in (30, 60, 90):
                ic_conditions = [
                    f"ic.cancel_effective_date >= CURRENT_DATE - INTERVAL '{days} days'",
                ]
                ic_params: list[Any] = []
                if state_filter:
                    ic_conditions.append("cm.physical_state = %s")
                    ic_params.append(state_filter)
                ic_where = "WHERE " + " AND ".join(ic_conditions)

                cur.execute(
                    f"""
                    SELECT COUNT(*) AS cnt
                    FROM entities.mv_fmcsa_insurance_cancellations ic
                    JOIN entities.mv_fmcsa_carrier_master cm
                        ON LTRIM(ic.usdot_number, '0') = cm.dot_number
                    {ic_where}
                    """,
                    ic_params,
                )
                cancel_counts[f"insurance_cancellations_last_{days}d"] = cur.fetchone()["cnt"]

    return {
        "total_carriers": total_carriers,
        "carriers_by_state": carriers_by_state,
        "carriers_with_alerts": carriers_with_alerts,
        "carriers_with_crashes": carriers_with_crashes,
        **authority_counts,
        **cancel_counts,
    }
