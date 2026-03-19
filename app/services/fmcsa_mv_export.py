"""FMCSA Carrier MV Export — CSV streaming from mv_fmcsa_carrier_master."""
from __future__ import annotations

import csv
import io
import logging
import threading
from typing import Any, Iterator

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


def _build_where(filters: dict[str, Any]) -> tuple[str, list[Any]]:
    """Build WHERE clause using the same filter set as search_carriers."""
    from app.services.fmcsa_mv_query import _build_carrier_where
    return _build_carrier_where(filters, alias="cm")


def stream_carriers_csv(
    *,
    filters: dict[str, Any],
    max_rows: int = 100_000,
) -> Iterator[str]:
    """Yield CSV lines for matching carriers from mv_fmcsa_carrier_master.

    Uses a server-side cursor to avoid loading all rows into memory.
    Raises ValueError if the result set exceeds max_rows.
    """
    where_clause, params = _build_where(filters)

    # Check count first
    count_sql = f"""
        SELECT COUNT(*)
        FROM entities.mv_fmcsa_carrier_master cm
        {where_clause}
    """
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total = cur.fetchone()[0]

    if total > max_rows:
        raise ValueError(
            f"Export would return {total} rows, exceeding the limit of {max_rows}. "
            "Add filters to narrow results."
        )

    # Stream results with server-side cursor
    data_sql = f"""
        SELECT *
        FROM entities.mv_fmcsa_carrier_master cm
        {where_clause}
        ORDER BY power_unit_count DESC NULLS LAST
    """

    with pool.connection() as conn:
        with conn.cursor(name="fmcsa_carrier_export_cursor") as cur:
            cur.itersize = 5000
            cur.execute(data_sql, params)

            columns = [desc[0] for desc in cur.description]

            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            yield buf.getvalue()

            while True:
                rows = cur.fetchmany(5000)
                if not rows:
                    break
                for row in rows:
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(row)
                    yield buf.getvalue()
