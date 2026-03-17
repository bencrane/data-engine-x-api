"""Federal Contract Leads — materialized view refresh and stats utilities."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

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


def refresh_federal_contract_leads(*, concurrent: bool = True) -> dict[str, Any]:
    """Refresh the mv_federal_contract_leads materialized view."""
    mode = "CONCURRENTLY" if concurrent else ""
    sql = f"REFRESH MATERIALIZED VIEW {mode} entities.mv_federal_contract_leads"

    logger.info("federal_leads_refresh: starting refresh (concurrent=%s)", concurrent)
    start = time.monotonic()

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            cur.execute(sql)
        conn.commit()

    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info("federal_leads_refresh: completed in %d ms", elapsed_ms)

    return {
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concurrent": concurrent,
        "elapsed_ms": elapsed_ms,
    }


def get_federal_leads_view_stats() -> dict[str, Any]:
    """Return aggregate stats from the materialized view."""
    sql = """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT recipient_uei) AS unique_companies,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee) AS first_time_awardees,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_dod_awardee AND dod_awards_count > 0) AS first_time_dod_awardees,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_nasa_awardee AND nasa_awards_count > 0) AS first_time_nasa_awardees,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_doe_awardee AND doe_awards_count > 0) AS first_time_doe_awardees,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_dhs_awardee AND dhs_awards_count > 0) AS first_time_dhs_awardees,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) / NULLIF(COUNT(DISTINCT recipient_uei), 0) AS average_obligation,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS median_obligation,
            SUM(CAST(NULLIF(potential_total_value_of_award, '') AS NUMERIC)) / NULLIF(COUNT(DISTINCT recipient_uei), 0) AS average_award_ceiling
        FROM entities.mv_federal_contract_leads
    """
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

    return {
        "total_rows": row[0],
        "unique_companies": row[1],
        "first_time_awardees": row[2],
        "first_time_dod_awardees": row[3],
        "first_time_nasa_awardees": row[4],
        "first_time_doe_awardees": row[5],
        "first_time_dhs_awardees": row[6],
        "average_obligation": float(row[7]) if row[7] is not None else 0.0,
        "median_obligation": float(row[8]) if row[8] is not None else 0.0,
        "average_award_ceiling": float(row[9]) if row[9] is not None else 0.0,
    }
