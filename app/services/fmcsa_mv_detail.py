"""FMCSA Carrier MV Detail — single-carrier profile from materialized views."""
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
            max_size=3,
            timeout=30.0,
        )
        return _pool


def get_carrier_detail(*, dot_number: str) -> dict[str, Any] | None:
    """Build a carrier profile from materialized views."""
    pool = _get_pool()

    # 1. Carrier master record
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM entities.mv_fmcsa_carrier_master WHERE dot_number = %s",
                [dot_number],
            )
            carrier_row = cur.fetchone()

    if carrier_row is None:
        return None

    carrier = dict(carrier_row)
    crash_summary = {
        "crash_count_12mo": carrier.get("crash_count_12mo", 0),
        "latest_crash_date": str(carrier["latest_crash_date"]) if carrier.get("latest_crash_date") else None,
        "fatal_crash_count_12mo": carrier.get("fatal_crash_count_12mo", 0),
    }

    # 2. Recent authority grants
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM entities.mv_fmcsa_authority_grants
                WHERE LTRIM(usdot_number, '0') = %s
                ORDER BY original_authority_action_served_date DESC
                LIMIT 10
                """,
                [dot_number],
            )
            recent_grants = [dict(r) for r in cur.fetchall()]

    # 3. Insurance policies — try MV first, fall back to raw table
    insurance_policies = _get_insurance_policies(pool, dot_number)

    return {
        "carrier": carrier,
        "insurance_policies": insurance_policies,
        "recent_authority_grants": recent_grants,
        "crash_summary": crash_summary,
    }


def _get_insurance_policies(pool: ConnectionPool, dot_number: str) -> list[dict[str, Any]]:
    """Get insurance policies via docket_number bridge.

    Tries mv_fmcsa_latest_insurance_policies first (migration 042).
    Falls back to raw insurance_policies table if the MV doesn't exist.
    """
    # Look up docket_number from carrier_registrations
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (usdot_number) docket_number
                FROM entities.carrier_registrations
                WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_registrations)
                  AND usdot_number = %s
                ORDER BY usdot_number, row_position
                """,
                [dot_number],
            )
            reg_row = cur.fetchone()

    if not reg_row or not reg_row.get("docket_number"):
        return []

    docket_number = reg_row["docket_number"]

    # Try the MV first
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM entities.mv_fmcsa_latest_insurance_policies
                    WHERE docket_number = %s
                    ORDER BY effective_date DESC NULLS LAST
                    """,
                    [docket_number],
                )
                return [dict(r) for r in cur.fetchall()]
    except Exception:
        logger.debug("mv_fmcsa_latest_insurance_policies not available, falling back to raw table")

    # Fallback: raw insurance_policies table
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT insurance_type_code, insurance_type_description,
                       bipd_maximum_dollar_limit_thousands_usd, policy_number,
                       effective_date, insurance_company_name, is_removal_signal
                FROM entities.insurance_policies
                WHERE docket_number = %s
                ORDER BY effective_date DESC NULLS LAST
                """,
                [docket_number],
            )
            return [dict(r) for r in cur.fetchall()]
