"""Federal Contract Leads — per-NAICS aggregate metrics."""
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


def _float(val: Any) -> float:
    return float(val) if val is not None else 0.0


def get_naics_metrics(
    *,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return one row per distinct NAICS code with aggregate metrics."""
    filters = filters or {}
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    where_conditions: list[str] = []
    where_params: list[Any] = []
    having_conditions: list[str] = []
    having_params: list[Any] = []

    if filters.get("naics_prefix"):
        where_conditions.append("naics_code LIKE %s")
        where_params.append(f"{filters['naics_prefix']}%")

    if filters.get("state"):
        where_conditions.append("recipient_state_code = %s")
        where_params.append(filters["state"])

    if filters.get("business_size"):
        where_conditions.append("contracting_officers_determination_of_business_size = %s")
        where_params.append(filters["business_size"])

    if filters.get("min_companies"):
        having_conditions.append("COUNT(DISTINCT recipient_uei) >= %s")
        having_params.append(int(filters["min_companies"]))

    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)

    having_clause = ""
    if having_conditions:
        having_clause = "HAVING " + " AND ".join(having_conditions)

    # Build the repeat_avg CTE with matching WHERE filters
    repeat_where_parts = ["is_first_time_awardee = FALSE"]
    repeat_params: list[Any] = []
    if filters.get("naics_prefix"):
        repeat_where_parts.append("naics_code LIKE %s")
        repeat_params.append(f"{filters['naics_prefix']}%")
    if filters.get("state"):
        repeat_where_parts.append("recipient_state_code = %s")
        repeat_params.append(filters["state"])
    if filters.get("business_size"):
        repeat_where_parts.append("contracting_officers_determination_of_business_size = %s")
        repeat_params.append(filters["business_size"])

    repeat_where = "WHERE " + " AND ".join(repeat_where_parts)

    sql = f"""
        WITH base AS (
            SELECT
                naics_code,
                MAX(naics_description) AS naics_description,
                COUNT(DISTINCT recipient_uei) AS total_companies,
                COUNT(DISTINCT contract_award_unique_key) AS total_awards,
                COUNT(*) AS total_transactions,
                SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS median_award_value,
                COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awardee_companies,
                SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = FALSE) AS repeat_awardee_total_obligated
            FROM entities.mv_federal_contract_leads
            {where_clause}
            GROUP BY naics_code
            {having_clause}
        ),
        repeat_avg AS (
            SELECT
                naics_code,
                AVG(total_awards_count) AS avg_awards_per_repeat_company
            FROM (
                SELECT DISTINCT naics_code, recipient_uei, total_awards_count
                FROM entities.mv_federal_contract_leads
                {repeat_where}
            ) sub
            GROUP BY naics_code
        )
        SELECT
            base.naics_code,
            base.naics_description,
            base.total_companies,
            base.total_awards,
            base.total_transactions,
            base.total_obligated,
            base.total_obligated / NULLIF(base.total_awards, 0) AS average_award_value,
            base.median_award_value,
            base.first_time_awardee_companies,
            base.total_companies - base.first_time_awardee_companies AS repeat_awardee_companies,
            base.repeat_awardee_total_obligated,
            repeat_avg.avg_awards_per_repeat_company AS repeat_awardee_avg_awards,
            COUNT(*) OVER() AS total_matched
        FROM base
        LEFT JOIN repeat_avg USING (naics_code)
        ORDER BY base.total_obligated DESC
        LIMIT %s OFFSET %s
    """

    params = where_params + having_params + repeat_params + [safe_limit, safe_offset]

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    total_matched = 0
    items: list[dict[str, Any]] = []
    for row in rows:
        total_matched = row.pop("total_matched", 0)
        items.append({
            "naics_code": row["naics_code"],
            "naics_description": row["naics_description"],
            "total_companies": row["total_companies"],
            "total_awards": row["total_awards"],
            "total_transactions": row["total_transactions"],
            "total_obligated": _float(row["total_obligated"]),
            "average_award_value": _float(row["average_award_value"]),
            "median_award_value": _float(row["median_award_value"]),
            "first_time_awardee_companies": row["first_time_awardee_companies"],
            "repeat_awardee_companies": row["repeat_awardee_companies"],
            "repeat_awardee_total_obligated": _float(row["repeat_awardee_total_obligated"]),
            "repeat_awardee_avg_awards": _float(row["repeat_awardee_avg_awards"]),
        })

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }


def get_naics_agency_breakdown(*, naics_code: str) -> list[dict[str, Any]]:
    """Return per-agency breakdown for a single NAICS code."""
    sql = """
        SELECT
            awarding_agency_code,
            MAX(awarding_agency_name) AS awarding_agency_name,
            COUNT(DISTINCT recipient_uei) AS total_companies,
            COUNT(DISTINCT contract_award_unique_key) AS total_awards,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awardee_companies
        FROM entities.mv_federal_contract_leads
        WHERE naics_code = %s
        GROUP BY awarding_agency_code
        ORDER BY SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, [naics_code])
            rows = cur.fetchall()

    return [
        {
            "awarding_agency_code": row["awarding_agency_code"],
            "awarding_agency_name": row["awarding_agency_name"],
            "total_companies": row["total_companies"],
            "total_awards": row["total_awards"],
            "total_obligated": _float(row["total_obligated"]),
            "first_time_awardee_companies": row["first_time_awardee_companies"],
            "repeat_awardee_companies": row["total_companies"] - row["first_time_awardee_companies"],
        }
        for row in rows
    ]
