"""SBA Loans Query — search and stats against typed materialized views."""
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
            max_size=4,
            timeout=30.0,
        )
        return _pool


# ---------------------------------------------------------------------------
# search_sba_loans
# ---------------------------------------------------------------------------

def search_sba_loans(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("state"):
        conditions.append("borrstate = %s")
        params.append(filters["state"])

    if filters.get("min_loan_amount") is not None:
        conditions.append("grossapproval_numeric >= %s")
        params.append(float(filters["min_loan_amount"]))

    if filters.get("max_loan_amount") is not None:
        conditions.append("grossapproval_numeric <= %s")
        params.append(float(filters["max_loan_amount"]))

    if filters.get("approval_date_from"):
        conditions.append("approvaldate_cast >= %s")
        params.append(filters["approval_date_from"])

    if filters.get("approval_date_to"):
        conditions.append("approvaldate_cast <= %s")
        params.append(filters["approval_date_to"])

    if filters.get("borrower_name"):
        conditions.append("borrname ILIKE %s")
        params.append(f"%{filters['borrower_name']}%")

    if filters.get("naics_code"):
        conditions.append("naicscode = %s")
        params.append(filters["naics_code"])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_matched
        FROM entities.mv_sba_loans_typed
        {where_clause}
        ORDER BY approvaldate_cast DESC NULLS LAST
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
        items.append(row)

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }


# ---------------------------------------------------------------------------
# get_sba_loan_stats
# ---------------------------------------------------------------------------

def _float(val: Any) -> float:
    return float(val) if val is not None else 0.0


def get_sba_loan_stats(*, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    pool = _get_pool()

    state_filter = filters.get("state")
    base_where = ""
    base_params: list[Any] = []
    if state_filter:
        base_where = "WHERE borrstate = %s"
        base_params = [state_filter]

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Total loans, volume, average
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS total_loans,
                    SUM(grossapproval_numeric) AS total_volume,
                    AVG(grossapproval_numeric) AS average_loan_amount
                FROM entities.mv_sba_loans_typed
                {base_where}
                """,
                base_params,
            )
            agg = cur.fetchone()

            # Loans by state (top 25)
            cur.execute(
                f"""
                SELECT
                    borrstate AS state,
                    COUNT(*) AS count,
                    SUM(grossapproval_numeric) AS total_volume
                FROM entities.mv_sba_loans_typed
                {base_where}
                GROUP BY borrstate
                ORDER BY COUNT(*) DESC
                LIMIT 25
                """,
                base_params,
            )
            loans_by_state = [
                {"state": r["state"], "count": r["count"], "total_volume": _float(r["total_volume"])}
                for r in cur.fetchall()
            ]

    return {
        "total_loans": agg["total_loans"],
        "total_volume": _float(agg["total_volume"]),
        "average_loan_amount": _float(agg["average_loan_amount"]),
        "loans_by_state": loans_by_state,
    }
