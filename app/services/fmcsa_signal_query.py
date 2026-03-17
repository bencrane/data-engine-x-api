"""FMCSA Carrier Signals — query service for signal detection results."""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()

ALL_SIGNAL_TYPES = [
    "new_carrier",
    "disappeared_carrier",
    "authority_granted",
    "authority_revoked",
    "insurance_added",
    "insurance_lapsed",
    "safety_worsened",
    "new_crash",
    "new_oos_order",
]

SEVERITY_ORDER = {"info": 0, "warning": 1, "critical": 2}


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


def _coerce_row(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce non-JSON-serializable types (date, datetime, Decimal, etc.)."""
    out = {}
    for k, v in row.items():
        if isinstance(v, (date, datetime)):
            out[k] = str(v)
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def _build_signal_where(
    filters: dict[str, Any],
) -> tuple[list[str], list[Any]]:
    """Build WHERE conditions + params for fmcsa_carrier_signals queries."""
    conditions: list[str] = []
    params: list[Any] = []

    # signal_types takes precedence over signal_type
    if filters.get("signal_types"):
        placeholders = ", ".join(["%s"] * len(filters["signal_types"]))
        conditions.append(f"signal_type IN ({placeholders})")
        params.extend(filters["signal_types"])
    elif filters.get("signal_type"):
        conditions.append("signal_type = %s")
        params.append(filters["signal_type"])

    if filters.get("severity"):
        conditions.append("severity = %s")
        params.append(filters["severity"])

    if filters.get("min_severity"):
        ms = filters["min_severity"]
        if ms == "critical":
            conditions.append("severity = %s")
            params.append("critical")
        elif ms == "warning":
            conditions.append("severity IN (%s, %s)")
            params.extend(["warning", "critical"])
        # min_severity='info' is a no-op (matches everything)

    if filters.get("dot_number"):
        conditions.append("dot_number = %s")
        params.append(filters["dot_number"])

    if filters.get("state"):
        conditions.append("physical_state = %s")
        params.append(filters["state"])

    if filters.get("feed_date"):
        conditions.append("feed_date = %s::DATE")
        params.append(filters["feed_date"])

    if filters.get("feed_date_from"):
        conditions.append("feed_date >= %s::DATE")
        params.append(filters["feed_date_from"])

    if filters.get("feed_date_to"):
        conditions.append("feed_date <= %s::DATE")
        params.append(filters["feed_date_to"])

    if filters.get("min_power_units") is not None:
        conditions.append("power_unit_count >= %s")
        params.append(filters["min_power_units"])

    if filters.get("legal_name_contains"):
        conditions.append("legal_name ILIKE %s")
        params.append(f"%{filters['legal_name_contains']}%")

    return conditions, params


def _conditions_to_where(conditions: list[str]) -> str:
    if not conditions:
        return ""
    return "WHERE " + " AND ".join(conditions)


def query_fmcsa_signals(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions, params = _build_signal_where(filters)
    where_clause = _conditions_to_where(conditions)

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_matched
        FROM entities.fmcsa_carrier_signals
        {where_clause}
        ORDER BY feed_date DESC, detected_at DESC, dot_number
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
        items.append(_coerce_row(row))

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }


def get_fmcsa_signal_summary(*, filters: dict[str, Any]) -> dict[str, Any]:
    pool = _get_pool()

    has_date_filter = any(
        filters.get(k) for k in ("feed_date", "feed_date_from", "feed_date_to")
    )

    # Auto-detect latest feed_date if no date filter provided
    resolved_feed_date: str | None = None
    if not has_date_filter:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT MAX(feed_date) AS max_date FROM entities.fmcsa_carrier_signals"
                )
                row = cur.fetchone()
                if row and row["max_date"] is not None:
                    resolved_feed_date = str(row["max_date"])

        if resolved_feed_date is None:
            # No data at all — return all-zeros summary
            by_type = {}
            for st in ALL_SIGNAL_TYPES:
                by_type[st] = {"count": 0, "critical": 0, "warning": 0, "info": 0}
            return {
                "feed_date": None,
                "total_signals": 0,
                "by_type": by_type,
                "by_severity": {"critical": 0, "warning": 0, "info": 0},
            }

        # Use the auto-detected date as an exact filter
        filters = dict(filters)
        filters["feed_date"] = resolved_feed_date

    conditions, params = _build_signal_where(filters)
    where_clause = _conditions_to_where(conditions)

    sql = f"""
        SELECT signal_type, severity, COUNT(*) AS cnt
        FROM entities.fmcsa_carrier_signals
        {where_clause}
        GROUP BY signal_type, severity
    """

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    # Build nested structure
    by_type: dict[str, dict[str, int]] = {}
    for st in ALL_SIGNAL_TYPES:
        by_type[st] = {"count": 0, "critical": 0, "warning": 0, "info": 0}

    by_severity = {"critical": 0, "warning": 0, "info": 0}
    total_signals = 0

    for row in rows:
        st = row["signal_type"]
        sev = row["severity"]
        cnt = row["cnt"]

        if st in by_type and sev in by_severity:
            by_type[st][sev] += cnt
            by_type[st]["count"] += cnt
            by_severity[sev] += cnt
            total_signals += cnt

    # Determine feed_date description for response
    if resolved_feed_date:
        feed_date_desc = resolved_feed_date
    elif filters.get("feed_date"):
        feed_date_desc = filters["feed_date"]
    elif filters.get("feed_date_from") and filters.get("feed_date_to"):
        feed_date_desc = f"{filters['feed_date_from']} to {filters['feed_date_to']}"
    elif filters.get("feed_date_from"):
        feed_date_desc = f"{filters['feed_date_from']} onwards"
    elif filters.get("feed_date_to"):
        feed_date_desc = f"up to {filters['feed_date_to']}"
    else:
        feed_date_desc = None

    return {
        "feed_date": feed_date_desc,
        "total_signals": total_signals,
        "by_type": by_type,
        "by_severity": by_severity,
    }


def query_carrier_signals(
    *,
    dot_number: str,
    filters: dict[str, Any],
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    # Start with dot_number filter
    conditions: list[str] = ["dot_number = %s"]
    params: list[Any] = [dot_number]

    if filters.get("signal_type"):
        conditions.append("signal_type = %s")
        params.append(filters["signal_type"])

    if filters.get("feed_date_from"):
        conditions.append("feed_date >= %s::DATE")
        params.append(filters["feed_date_from"])

    if filters.get("feed_date_to"):
        conditions.append("feed_date <= %s::DATE")
        params.append(filters["feed_date_to"])

    where_clause = _conditions_to_where(conditions)

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_matched
        FROM entities.fmcsa_carrier_signals
        {where_clause}
        ORDER BY feed_date DESC, detected_at DESC
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
        items.append(_coerce_row(row))

    return {
        "dot_number": dot_number,
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }
