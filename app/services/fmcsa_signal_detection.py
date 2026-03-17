"""FMCSA Signal Detection Engine — daily diff layer for carrier change signals."""
from __future__ import annotations

import json
import logging
import threading
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

SIGNAL_TABLE = "entities.fmcsa_carrier_signals"

BASIC_PERCENTILE_COLUMNS = [
    "unsafe_driving_percentile",
    "hours_of_service_percentile",
    "driver_fitness_percentile",
    "controlled_substances_alcohol_percentile",
    "vehicle_maintenance_percentile",
]

BASIC_NAMES = [
    "unsafe_driving",
    "hours_of_service",
    "driver_fitness",
    "controlled_substances_alcohol",
    "vehicle_maintenance",
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


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    return val


def _json_safe(obj: Any) -> Any:
    """Make a value JSON-serializable (handle Decimal, date, etc.)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_two_latest_feed_dates(pool: ConnectionPool, table: str) -> tuple[str, str] | None:
    """Return (latest, previous) feed_date for a feed-date-based table, or None."""
    sql = f"SELECT DISTINCT feed_date FROM {table} ORDER BY feed_date DESC LIMIT 2"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    if len(rows) < 2:
        return None
    return (str(rows[0]["feed_date"]), str(rows[1]["feed_date"]))


def _get_two_latest_observed_at(pool: ConnectionPool, table: str) -> tuple[str, str] | None:
    """Return (latest, previous) source_observed_at for a fingerprint-based table, or None."""
    sql = f"SELECT DISTINCT source_observed_at FROM {table} ORDER BY source_observed_at DESC LIMIT 2"
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
    if len(rows) < 2:
        return None
    return (str(rows[0]["source_observed_at"]), str(rows[1]["source_observed_at"]))


def enrich_carriers(pool: ConnectionPool, dot_numbers: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-lookup census fields for a list of DOT numbers."""
    if not dot_numbers:
        return {}
    unique_dots = list(set(dot_numbers))
    placeholders = ",".join(["%s"] * len(unique_dots))
    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (dot_number)
                dot_number, legal_name, physical_state, power_unit_count, driver_total
            FROM entities.motor_carrier_census_records
            WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
              AND dot_number IN ({placeholders})
            ORDER BY dot_number, row_position
        )
        SELECT * FROM latest
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, unique_dots)
            rows = cur.fetchall()
    return {
        row["dot_number"]: {
            "legal_name": row["legal_name"],
            "physical_state": row["physical_state"],
            "power_unit_count": row["power_unit_count"],
            "driver_total": row["driver_total"],
        }
        for row in rows
    }


def resolve_docket_to_dot(pool: ConnectionPool, docket_numbers: list[str]) -> dict[str, str]:
    """Resolve docket numbers to DOT numbers via carrier_registrations."""
    if not docket_numbers:
        return {}
    unique_dockets = list(set(docket_numbers))
    placeholders = ",".join(["%s"] * len(unique_dockets))
    sql = f"""
        SELECT DISTINCT ON (docket_number) docket_number, usdot_number
        FROM entities.carrier_registrations
        WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_registrations)
          AND docket_number IN ({placeholders})
          AND usdot_number IS NOT NULL
        ORDER BY docket_number, row_position
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, unique_dockets)
            rows = cur.fetchall()
    return {row["docket_number"]: row["usdot_number"] for row in rows}


# ---------------------------------------------------------------------------
# Detection Functions — Pattern A (feed-date-based)
# ---------------------------------------------------------------------------


def detect_new_carriers(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    dates = _get_two_latest_feed_dates(pool, "entities.motor_carrier_census_records")
    if not dates:
        return []
    latest, previous = dates
    sql = """
        WITH today AS (
            SELECT DISTINCT ON (dot_number)
                dot_number, carrier_operation_code, physical_state,
                power_unit_count, driver_total, source_feed_name
            FROM entities.motor_carrier_census_records
            WHERE feed_date = %s
            ORDER BY dot_number, row_position
        ),
        yesterday AS (
            SELECT DISTINCT ON (dot_number) dot_number
            FROM entities.motor_carrier_census_records
            WHERE feed_date = %s
            ORDER BY dot_number, row_position
        )
        SELECT t.*
        FROM today t
        LEFT JOIN yesterday y ON t.dot_number = y.dot_number
        WHERE y.dot_number IS NULL
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest, previous])
            rows = cur.fetchall()
    return [
        {
            "signal_type": "new_carrier",
            "feed_date": latest,
            "dot_number": row["dot_number"],
            "entity_key": row["dot_number"],
            "severity": "info",
            "after_values": _json_safe({
                "carrier_operation_code": row["carrier_operation_code"],
                "physical_state": row["physical_state"],
                "power_unit_count": row["power_unit_count"],
                "driver_total": row["driver_total"],
            }),
            "source_table": "motor_carrier_census_records",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


def detect_disappeared_carriers(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    dates = _get_two_latest_feed_dates(pool, "entities.motor_carrier_census_records")
    if not dates:
        return []
    latest, previous = dates
    sql = """
        WITH today AS (
            SELECT DISTINCT ON (dot_number) dot_number
            FROM entities.motor_carrier_census_records
            WHERE feed_date = %s
            ORDER BY dot_number, row_position
        ),
        yesterday AS (
            SELECT DISTINCT ON (dot_number)
                dot_number, carrier_operation_code, physical_state,
                power_unit_count, driver_total, source_feed_name
            FROM entities.motor_carrier_census_records
            WHERE feed_date = %s
            ORDER BY dot_number, row_position
        )
        SELECT y.*
        FROM yesterday y
        LEFT JOIN today t ON y.dot_number = t.dot_number
        WHERE t.dot_number IS NULL
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest, previous])
            rows = cur.fetchall()
    return [
        {
            "signal_type": "disappeared_carrier",
            "feed_date": latest,
            "dot_number": row["dot_number"],
            "entity_key": row["dot_number"],
            "severity": "warning",
            "before_values": _json_safe({
                "carrier_operation_code": row["carrier_operation_code"],
                "physical_state": row["physical_state"],
                "power_unit_count": row["power_unit_count"],
                "driver_total": row["driver_total"],
            }),
            "source_table": "motor_carrier_census_records",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


def detect_safety_worsened(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    dates = _get_two_latest_feed_dates(pool, "entities.carrier_safety_basic_percentiles")
    if not dates:
        return []
    latest, previous = dates
    pct_cols = ", ".join(BASIC_PERCENTILE_COLUMNS)
    sql = f"""
        WITH today AS (
            SELECT DISTINCT ON (dot_number)
                dot_number, {pct_cols}, source_feed_name
            FROM entities.carrier_safety_basic_percentiles
            WHERE feed_date = %s AND dot_number IS NOT NULL
            ORDER BY dot_number, row_position
        ),
        yesterday AS (
            SELECT DISTINCT ON (dot_number)
                dot_number, {pct_cols}
            FROM entities.carrier_safety_basic_percentiles
            WHERE feed_date = %s AND dot_number IS NOT NULL
            ORDER BY dot_number, row_position
        )
        SELECT t.dot_number, t.source_feed_name,
            {", ".join(f"t.{c} AS today_{c}, y.{c} AS yesterday_{c}" for c in BASIC_PERCENTILE_COLUMNS)}
        FROM today t
        JOIN yesterday y ON t.dot_number = y.dot_number
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest, previous])
            rows = cur.fetchall()

    signals: list[dict[str, Any]] = []
    for row in rows:
        worsened: list[dict[str, Any]] = []
        max_severity = "warning"
        for name in BASIC_NAMES:
            col = f"{name}_percentile"
            today_val = _decimal_to_float(row[f"today_{col}"])
            yesterday_val = _decimal_to_float(row[f"yesterday_{col}"])
            if today_val is None or yesterday_val is None:
                continue
            crossed_90 = yesterday_val < 90 and today_val >= 90
            crossed_75 = yesterday_val < 75 and today_val >= 75
            if crossed_90:
                max_severity = "critical"
                worsened.append({
                    "basic": name,
                    "previous": yesterday_val,
                    "current": today_val,
                    "threshold_crossed": 90,
                })
            elif crossed_75:
                worsened.append({
                    "basic": name,
                    "previous": yesterday_val,
                    "current": today_val,
                    "threshold_crossed": 75,
                })
        if not worsened:
            continue
        before_vals = {f"{name}_percentile": _decimal_to_float(row[f"yesterday_{name}_percentile"]) for name in BASIC_NAMES}
        after_vals = {f"{name}_percentile": _decimal_to_float(row[f"today_{name}_percentile"]) for name in BASIC_NAMES}
        signals.append({
            "signal_type": "safety_worsened",
            "feed_date": latest,
            "dot_number": row["dot_number"],
            "entity_key": row["dot_number"],
            "severity": max_severity,
            "before_values": _json_safe(before_vals),
            "after_values": _json_safe(after_vals),
            "signal_details": _json_safe({"worsened_basics": worsened}),
            "source_table": "carrier_safety_basic_percentiles",
            "source_feed_name": row["source_feed_name"],
        })
    return signals


def detect_new_crashes(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    dates = _get_two_latest_feed_dates(pool, "entities.commercial_vehicle_crashes")
    if not dates:
        return []
    latest, previous = dates
    sql = """
        WITH today AS (
            SELECT crash_id, dot_number, report_date, state, city,
                   fatalities, injuries, tow_away, hazmat_released, source_feed_name
            FROM entities.commercial_vehicle_crashes
            WHERE feed_date = %s
        ),
        yesterday AS (
            SELECT DISTINCT crash_id
            FROM entities.commercial_vehicle_crashes
            WHERE feed_date = %s
        )
        SELECT t.*
        FROM today t
        LEFT JOIN yesterday y ON t.crash_id = y.crash_id
        WHERE y.crash_id IS NULL AND t.crash_id IS NOT NULL
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest, previous])
            rows = cur.fetchall()
    return [
        {
            "signal_type": "new_crash",
            "feed_date": latest,
            "dot_number": row["dot_number"] or "UNKNOWN",
            "entity_key": row["crash_id"],
            "severity": "critical" if (row.get("fatalities") or 0) > 0 else "warning",
            "after_values": _json_safe({
                "report_date": row["report_date"],
                "state": row["state"],
                "city": row["city"],
                "fatalities": row["fatalities"],
                "injuries": row["injuries"],
                "tow_away": row["tow_away"],
                "hazmat_released": row["hazmat_released"],
            }),
            "source_table": "commercial_vehicle_crashes",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


def detect_new_oos_orders(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    dates = _get_two_latest_feed_dates(pool, "entities.out_of_service_orders")
    if not dates:
        return []
    latest, previous = dates
    sql = """
        WITH today AS (
            SELECT dot_number, oos_date, oos_reason, status, source_feed_name
            FROM entities.out_of_service_orders
            WHERE feed_date = %s
        ),
        yesterday AS (
            SELECT dot_number, oos_date, oos_reason
            FROM entities.out_of_service_orders
            WHERE feed_date = %s
        )
        SELECT t.*
        FROM today t
        LEFT JOIN yesterday y
            ON t.dot_number = y.dot_number
            AND t.oos_date = y.oos_date
            AND t.oos_reason = y.oos_reason
        WHERE y.dot_number IS NULL AND t.dot_number IS NOT NULL
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest, previous])
            rows = cur.fetchall()
    return [
        {
            "signal_type": "new_oos_order",
            "feed_date": latest,
            "dot_number": row["dot_number"],
            "entity_key": f"{row['dot_number']}:{row['oos_date']}",
            "severity": "critical",
            "after_values": _json_safe({
                "oos_date": row["oos_date"],
                "oos_reason": row["oos_reason"],
                "status": row["status"],
            }),
            "source_table": "out_of_service_orders",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# Detection Functions — Pattern B (fingerprint-based)
# ---------------------------------------------------------------------------


def detect_authority_granted(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    window = _get_two_latest_observed_at(pool, "entities.operating_authority_histories")
    if not window:
        return []
    latest_obs, _ = window
    sql = """
        SELECT record_fingerprint, usdot_number, docket_number,
               operating_authority_type, original_authority_action_description,
               final_authority_action_description, final_authority_decision_date,
               final_authority_served_date, source_feed_name
        FROM entities.operating_authority_histories
        WHERE first_observed_at >= %s
          AND (
              final_authority_action_description ILIKE '%%GRANT%%'
              OR original_authority_action_description ILIKE '%%GRANT%%'
          )
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest_obs])
            rows = cur.fetchall()
    return [
        {
            "signal_type": "authority_granted",
            "feed_date": feed_date,
            "dot_number": row["usdot_number"] or "UNKNOWN",
            "docket_number": row["docket_number"],
            "entity_key": row["record_fingerprint"],
            "severity": "info",
            "after_values": _json_safe({
                "operating_authority_type": row["operating_authority_type"],
                "action_description": row["final_authority_action_description"] or row["original_authority_action_description"],
                "decision_date": row["final_authority_decision_date"],
                "served_date": row["final_authority_served_date"],
            }),
            "source_table": "operating_authority_histories",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


def detect_authority_revoked(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    window = _get_two_latest_observed_at(pool, "entities.operating_authority_revocations")
    if not window:
        return []
    latest_obs, _ = window
    sql = """
        SELECT record_fingerprint, usdot_number, docket_number,
               operating_authority_registration_type, revocation_type,
               serve_date, effective_date, source_feed_name
        FROM entities.operating_authority_revocations
        WHERE first_observed_at >= %s
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest_obs])
            rows = cur.fetchall()
    return [
        {
            "signal_type": "authority_revoked",
            "feed_date": feed_date,
            "dot_number": row["usdot_number"] or "UNKNOWN",
            "docket_number": row["docket_number"],
            "entity_key": row["record_fingerprint"],
            "severity": "warning",
            "after_values": _json_safe({
                "registration_type": row["operating_authority_registration_type"],
                "revocation_type": row["revocation_type"],
                "serve_date": row["serve_date"],
                "effective_date": row["effective_date"],
            }),
            "source_table": "operating_authority_revocations",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


def detect_insurance_added(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    window = _get_two_latest_observed_at(pool, "entities.insurance_policies")
    if not window:
        return []
    latest_obs, _ = window
    sql = """
        SELECT record_fingerprint, docket_number, insurance_type_code,
               insurance_type_description, bipd_maximum_dollar_limit_thousands_usd,
               policy_number, effective_date, insurance_company_name, source_feed_name
        FROM entities.insurance_policies
        WHERE first_observed_at >= %s
          AND is_removal_signal = FALSE
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest_obs])
            rows = cur.fetchall()

    docket_nums = [r["docket_number"] for r in rows if r["docket_number"]]
    docket_dot_map = resolve_docket_to_dot(pool, docket_nums)

    return [
        {
            "signal_type": "insurance_added",
            "feed_date": feed_date,
            "dot_number": docket_dot_map.get(row["docket_number"], "UNKNOWN"),
            "docket_number": row["docket_number"],
            "entity_key": row["record_fingerprint"],
            "severity": "info",
            "after_values": _json_safe({
                "insurance_type": row["insurance_type_description"] or row["insurance_type_code"],
                "bipd_limit_thousands_usd": row["bipd_maximum_dollar_limit_thousands_usd"],
                "policy_number": row["policy_number"],
                "effective_date": row["effective_date"],
                "insurer": row["insurance_company_name"],
            }),
            "source_table": "insurance_policies",
            "source_feed_name": row["source_feed_name"],
        }
        for row in rows
    ]


def detect_insurance_lapsed(feed_date: str, pool: ConnectionPool) -> list[dict[str, Any]]:
    window = _get_two_latest_observed_at(pool, "entities.insurance_policies")
    if not window:
        return []
    latest_obs, previous_obs = window
    # Two cases: explicit removal signals newly appeared, or records that disappeared
    sql = """
        (
            SELECT record_fingerprint, docket_number, insurance_type_code,
                   insurance_type_description, bipd_maximum_dollar_limit_thousands_usd,
                   policy_number, effective_date, insurance_company_name,
                   is_removal_signal, source_feed_name
            FROM entities.insurance_policies
            WHERE is_removal_signal = TRUE
              AND first_observed_at >= %s
        )
        UNION ALL
        (
            SELECT record_fingerprint, docket_number, insurance_type_code,
                   insurance_type_description, bipd_maximum_dollar_limit_thousands_usd,
                   policy_number, effective_date, insurance_company_name,
                   is_removal_signal, source_feed_name
            FROM entities.insurance_policies
            WHERE last_observed_at < %s
              AND last_observed_at >= %s
              AND is_removal_signal = FALSE
        )
    """
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [latest_obs, latest_obs, previous_obs])
            rows = cur.fetchall()

    docket_nums = [r["docket_number"] for r in rows if r["docket_number"]]
    docket_dot_map = resolve_docket_to_dot(pool, docket_nums)

    signals: list[dict[str, Any]] = []
    for row in rows:
        is_bipd = (row.get("insurance_type_code") or "").upper() in ("BIPD", "BL")
        severity = "critical" if is_bipd else "warning"
        signals.append({
            "signal_type": "insurance_lapsed",
            "feed_date": feed_date,
            "dot_number": docket_dot_map.get(row["docket_number"], "UNKNOWN"),
            "docket_number": row["docket_number"],
            "entity_key": row["record_fingerprint"],
            "severity": severity,
            "before_values": _json_safe({
                "insurance_type": row["insurance_type_description"] or row["insurance_type_code"],
                "bipd_limit_thousands_usd": row["bipd_maximum_dollar_limit_thousands_usd"],
                "policy_number": row["policy_number"],
                "effective_date": row["effective_date"],
                "insurer": row["insurance_company_name"],
            }),
            "source_table": "insurance_policies",
            "source_feed_name": row["source_feed_name"],
        })
    return signals


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

ALL_DETECTORS = [
    detect_new_carriers,
    detect_disappeared_carriers,
    detect_authority_granted,
    detect_authority_revoked,
    detect_insurance_added,
    detect_insurance_lapsed,
    detect_safety_worsened,
    detect_new_crashes,
    detect_new_oos_orders,
]


def _persist_signals(pool: ConnectionPool, signals: list[dict[str, Any]]) -> int:
    """Insert signals with ON CONFLICT DO NOTHING. Returns count of rows inserted."""
    if not signals:
        return 0
    columns = [
        "signal_type", "feed_date", "dot_number", "docket_number", "entity_key",
        "severity", "legal_name", "physical_state", "power_unit_count", "driver_total",
        "before_values", "after_values", "signal_details", "source_table", "source_feed_name",
    ]
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))
    sql = f"""
        INSERT INTO {SIGNAL_TABLE} ({col_list})
        VALUES ({placeholders})
        ON CONFLICT (signal_type, feed_date, entity_key) DO NOTHING
    """
    inserted = 0
    with pool.connection() as conn:
        with conn.cursor() as cur:
            for sig in signals:
                params = [
                    sig.get("signal_type"),
                    sig.get("feed_date"),
                    sig.get("dot_number"),
                    sig.get("docket_number"),
                    sig.get("entity_key"),
                    sig.get("severity"),
                    sig.get("legal_name"),
                    sig.get("physical_state"),
                    sig.get("power_unit_count"),
                    sig.get("driver_total"),
                    json.dumps(sig["before_values"]) if sig.get("before_values") else None,
                    json.dumps(sig["after_values"]) if sig.get("after_values") else None,
                    json.dumps(sig["signal_details"]) if sig.get("signal_details") else None,
                    sig.get("source_table"),
                    sig.get("source_feed_name"),
                ]
                cur.execute(sql, params)
                inserted += cur.rowcount
        conn.commit()
    return inserted


def run_signal_detection(feed_date: str) -> dict[str, Any]:
    """Run all 9 signal detectors, enrich, persist, and return summary."""
    pool = _get_pool()
    counts: dict[str, int] = {}
    total_signals = 0

    for detector in ALL_DETECTORS:
        name = detector.__name__.replace("detect_", "")
        try:
            signals = detector(feed_date, pool)
        except Exception:
            logger.exception("Signal detector %s failed", name)
            counts[name] = 0
            continue

        if signals:
            # Enrich with carrier census data
            dot_numbers = [s["dot_number"] for s in signals if s["dot_number"] != "UNKNOWN"]
            enrichment = enrich_carriers(pool, dot_numbers)
            for sig in signals:
                carrier = enrichment.get(sig["dot_number"], {})
                sig["legal_name"] = carrier.get("legal_name")
                sig["physical_state"] = carrier.get("physical_state")
                sig["power_unit_count"] = carrier.get("power_unit_count")
                sig["driver_total"] = carrier.get("driver_total")

            inserted = _persist_signals(pool, signals)
            counts[name] = inserted
            total_signals += inserted
        else:
            counts[name] = 0

        logger.info("Signal detector %s: %d signals", name, counts[name])

    return {
        "feed_date": feed_date,
        "total_signals": total_signals,
        "counts": counts,
    }
