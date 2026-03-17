"""SBA 7(a) Loans — query service against entities.sba_7a_loans."""
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


def query_sba_loans(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("naics_prefix"):
        conditions.append("naicscode LIKE %s")
        params.append(f"{filters['naics_prefix']}%")

    if filters.get("state"):
        conditions.append("borrstate = %s")
        params.append(filters["state"])

    if filters.get("min_loan_amount"):
        conditions.append("CAST(grossapproval AS NUMERIC) >= %s")
        params.append(float(filters["min_loan_amount"]))

    if filters.get("max_loan_amount"):
        conditions.append("CAST(grossapproval AS NUMERIC) <= %s")
        params.append(float(filters["max_loan_amount"]))

    if filters.get("approval_date_from"):
        conditions.append("TO_DATE(approvaldate, 'MM/DD/YYYY') >= %s::DATE")
        params.append(filters["approval_date_from"])

    if filters.get("approval_date_to"):
        conditions.append("TO_DATE(approvaldate, 'MM/DD/YYYY') <= %s::DATE")
        params.append(filters["approval_date_to"])

    if filters.get("business_age"):
        conditions.append("businessage = %s")
        params.append(filters["business_age"])

    if filters.get("business_type"):
        conditions.append("businesstype = %s")
        params.append(filters["business_type"])

    if filters.get("lender_name"):
        conditions.append("bankname ILIKE %s")
        params.append(f"%{filters['lender_name']}%")

    if filters.get("loan_status"):
        conditions.append("loanstatus = %s")
        params.append(filters["loan_status"])

    if filters.get("borrower_name"):
        conditions.append("borrname ILIKE %s")
        params.append(f"%{filters['borrower_name']}%")

    if filters.get("min_jobs"):
        conditions.append("CAST(jobssupported AS INTEGER) >= %s")
        params.append(int(filters["min_jobs"]))

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_matched
        FROM entities.sba_7a_loans
        {where_clause}
        ORDER BY approvaldate DESC
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


def get_sba_loans_stats() -> dict[str, Any]:
    """Return aggregate stats from sba_7a_loans."""
    sql = """
        SELECT
            COUNT(*) AS total_rows,
            COUNT(DISTINCT borrname) AS unique_borrowers,
            SUM(CAST(grossapproval AS NUMERIC)) AS total_loan_volume,
            COUNT(DISTINCT naicscode) AS distinct_naics_codes,
            COUNT(DISTINCT borrstate) AS distinct_states
        FROM entities.sba_7a_loans
    """
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

    return {
        "total_rows": row[0],
        "unique_borrowers": row[1],
        "total_loan_volume": float(row[2]) if row[2] is not None else 0.0,
        "distinct_naics_codes": row[3],
        "distinct_states": row[4],
    }
