"""FMCSA — consolidated analytics (new authorities, insurance cancellations)."""
from __future__ import annotations

import logging
import re
import threading
from datetime import date, timedelta
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


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(val: str, name: str) -> None:
    if not _DATE_RE.match(val):
        raise ValueError(f"{name} must be YYYY-MM-DD, got: {val!r}")


def _resolve_date_range(p: dict[str, Any]) -> tuple[str, str]:
    """Resolve date range from explicit dates or months-back parameter."""
    date_from = p.get("date_from")
    date_to = p.get("date_to")
    if date_from and date_to:
        _validate_date(date_from, "date_from")
        _validate_date(date_to, "date_to")
        return date_from, date_to
    months = max(1, min(int(p.get("months", 6)), 24))
    cutoff = date.today() - timedelta(days=months * 31)
    return cutoff.isoformat(), date.today().isoformat()


_QUERY_DISPATCH: dict[str, Any] = {}


def run_fmcsa_analytics(
    *,
    query_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch to the appropriate FMCSA analytics query function."""
    handler = _QUERY_DISPATCH.get(query_type)
    if handler is None:
        raise ValueError(f"Unknown query_type: {query_type!r}")
    return handler(params or {})


def _execute(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET statement_timeout = '60s'")
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.execute("RESET statement_timeout")
    return rows


# ── Query Type 1: new_authorities_by_month ─────────────────────────────────


def _new_authorities_by_month(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(p)

    sql = """
        SELECT
            TO_CHAR(final_authority_decision_date, 'YYYY-MM') AS month,
            COUNT(*) AS new_authorities,
            COUNT(DISTINCT usdot_number) AS unique_carriers
        FROM entities.mv_fmcsa_authority_grants
        WHERE final_authority_decision_date >= %s
          AND final_authority_decision_date <= %s
        GROUP BY month
        ORDER BY month ASC
    """

    rows = _execute(sql, [date_from, date_to])
    return {
        "query_type": "new_authorities_by_month",
        "date_range": {"from": date_from, "to": date_to},
        "items": [
            {
                "month": r["month"],
                "new_authorities": r["new_authorities"],
                "unique_carriers": r["unique_carriers"],
            }
            for r in rows
        ],
    }


# ── Query Type 2: insurance_cancellations_by_month ─────────────────────────


def _insurance_cancellations_by_month(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _resolve_date_range(p)

    # Primary source: materialized view (pre-filtered to non-null cancel dates)
    primary_sql = """
        SELECT
            TO_CHAR(cancel_effective_date, 'YYYY-MM') AS month,
            COUNT(*) AS cancellations,
            COUNT(DISTINCT usdot_number) AS unique_carriers
        FROM entities.mv_fmcsa_insurance_cancellations
        WHERE cancel_effective_date >= %s
          AND cancel_effective_date <= %s
        GROUP BY month
        ORDER BY month ASC
    """

    rows = _execute(primary_sql, [date_from, date_to])
    source = "mv_fmcsa_insurance_cancellations"

    # Fallback to fmcsa_carrier_signals if primary returns nothing
    if not rows:
        fallback_sql = """
            SELECT
                TO_CHAR(feed_date, 'YYYY-MM') AS month,
                COUNT(*) AS cancellations,
                COUNT(DISTINCT dot_number) AS unique_carriers
            FROM entities.fmcsa_carrier_signals
            WHERE signal_type = 'insurance_lapsed'
              AND feed_date >= %s
              AND feed_date <= %s
            GROUP BY month
            ORDER BY month ASC
        """
        rows = _execute(fallback_sql, [date_from, date_to])
        source = "fmcsa_carrier_signals"

    return {
        "query_type": "insurance_cancellations_by_month",
        "date_range": {"from": date_from, "to": date_to},
        "source": source,
        "items": [
            {
                "month": r["month"],
                "cancellations": r["cancellations"],
                "unique_carriers": r["unique_carriers"],
            }
            for r in rows
        ],
    }


# ── Dispatch registration ──────────────────────────────────────────────────

_QUERY_DISPATCH.update({
    "new_authorities_by_month": _new_authorities_by_month,
    "insurance_cancellations_by_month": _insurance_cancellations_by_month,
})
