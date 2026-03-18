"""FMCSA — monthly summary analytics (new authorities, insurance cancellations)."""
from __future__ import annotations

import logging
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


def get_fmcsa_monthly_summary(
    *,
    months: int = 6,
) -> dict[str, Any]:
    """New operating authorities granted and insurance cancellations per month.

    months: how many months back to look (default 6).

    Queries pre-filtered materialized views (mv_fmcsa_authority_grants,
    mv_fmcsa_insurance_cancellations) to avoid full base table scans.
    """
    safe_months = max(1, min(months, 24))
    cutoff_date = date.today() - timedelta(days=safe_months * 31)

    new_auth_sql = """
        SELECT
            TO_CHAR(final_authority_decision_date, 'YYYY-MM') AS month,
            COUNT(*) AS count
        FROM entities.mv_fmcsa_authority_grants
        WHERE final_authority_decision_date >= %s
        GROUP BY month
        ORDER BY month ASC
    """

    cancel_sql = """
        SELECT
            TO_CHAR(cancel_effective_date, 'YYYY-MM') AS month,
            COUNT(*) AS count
        FROM entities.mv_fmcsa_insurance_cancellations
        WHERE cancel_effective_date >= %s
        GROUP BY month
        ORDER BY month ASC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET statement_timeout = '30s'")

            cur.execute(new_auth_sql, [cutoff_date])
            new_auth_rows = cur.fetchall()

            cur.execute(cancel_sql, [cutoff_date])
            cancel_rows = cur.fetchall()

            cur.execute("RESET statement_timeout")

    return {
        "new_authorities": [
            {"month": row["month"], "count": row["count"]}
            for row in new_auth_rows
        ],
        "insurance_cancellations": [
            {"month": row["month"], "count": row["count"]}
            for row in cancel_rows
        ],
        "months_requested": safe_months,
    }
