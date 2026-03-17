"""Federal Contract Leads — vertical summary by NAICS category."""
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


def get_vertical_summary() -> list[dict[str, Any]]:
    """Return aggregated vertical stats from the federal contract leads materialized view."""
    sql = """
        SELECT
            CASE
                WHEN naics_code LIKE '31%%' OR naics_code LIKE '32%%' OR naics_code LIKE '33%%' THEN 'Manufacturing'
                WHEN naics_code LIKE '23%%' THEN 'Construction'
                WHEN naics_code LIKE '54%%' THEN 'IT & Professional Services'
                WHEN naics_code LIKE '62%%' THEN 'Healthcare & Social Assistance'
                WHEN naics_code LIKE '48%%' OR naics_code LIKE '49%%' THEN 'Transportation & Warehousing'
                WHEN naics_code LIKE '56%%' THEN 'Admin & Staffing Services'
                ELSE 'All Other'
            END AS vertical,
            COUNT(*) AS total_rows,
            COUNT(DISTINCT recipient_uei) AS unique_companies,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awardees,
            COUNT(DISTINCT recipient_uei) - COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS repeat_awardees,
            SUM(CAST(federal_action_obligation AS NUMERIC)) AS total_obligated
        FROM entities.mv_federal_contract_leads
        GROUP BY vertical
        ORDER BY total_rows DESC
    """
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            rows = cur.fetchall()

    return [
        {
            "vertical": row["vertical"],
            "total_rows": row["total_rows"],
            "unique_companies": row["unique_companies"],
            "first_time_awardees": row["first_time_awardees"],
            "repeat_awardees": row["repeat_awardees"],
            "total_obligated": float(row["total_obligated"]) if row["total_obligated"] is not None else 0.0,
        }
        for row in rows
    ]
