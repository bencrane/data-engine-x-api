"""FMCSA Analytics — materialized view refresh utilities."""
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


def refresh_fmcsa_authority_grants(*, concurrent: bool = True) -> dict[str, Any]:
    """Refresh the mv_fmcsa_authority_grants materialized view."""
    mode = "CONCURRENTLY" if concurrent else ""
    sql = f"REFRESH MATERIALIZED VIEW {mode} entities.mv_fmcsa_authority_grants"

    logger.info("fmcsa_authority_grants_refresh: starting refresh (concurrent=%s)", concurrent)
    start = time.monotonic()

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            cur.execute(sql)
        conn.commit()

    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info("fmcsa_authority_grants_refresh: completed in %d ms", elapsed_ms)

    return {
        "view": "mv_fmcsa_authority_grants",
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concurrent": concurrent,
        "elapsed_ms": elapsed_ms,
    }


def refresh_fmcsa_insurance_cancellations(*, concurrent: bool = True) -> dict[str, Any]:
    """Refresh the mv_fmcsa_insurance_cancellations materialized view."""
    mode = "CONCURRENTLY" if concurrent else ""
    sql = f"REFRESH MATERIALIZED VIEW {mode} entities.mv_fmcsa_insurance_cancellations"

    logger.info("fmcsa_insurance_cancellations_refresh: starting refresh (concurrent=%s)", concurrent)
    start = time.monotonic()

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '1800s'")
            cur.execute(sql)
        conn.commit()

    elapsed_ms = int((time.monotonic() - start) * 1000)
    logger.info("fmcsa_insurance_cancellations_refresh: completed in %d ms", elapsed_ms)

    return {
        "view": "mv_fmcsa_insurance_cancellations",
        "refreshed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concurrent": concurrent,
        "elapsed_ms": elapsed_ms,
    }


def refresh_all_fmcsa_analytics(*, concurrent: bool = True) -> dict[str, Any]:
    """Refresh both FMCSA analytics materialized views sequentially."""
    start = time.monotonic()

    authority_result = refresh_fmcsa_authority_grants(concurrent=concurrent)
    insurance_result = refresh_fmcsa_insurance_cancellations(concurrent=concurrent)

    total_elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "authority_grants": authority_result,
        "insurance_cancellations": insurance_result,
        "total_elapsed_ms": total_elapsed_ms,
    }
