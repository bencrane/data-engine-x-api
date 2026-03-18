"""Federal Contract Leads — flexible insight queries with date + awardee-type filters."""
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


VERTICAL_CASE = """
CASE
    WHEN naics_code LIKE '31%%' OR naics_code LIKE '32%%' OR naics_code LIKE '33%%' THEN 'Manufacturing'
    WHEN naics_code LIKE '23%%' THEN 'Construction'
    WHEN naics_code LIKE '54%%' THEN 'IT & Professional Services'
    WHEN naics_code LIKE '62%%' THEN 'Healthcare & Social Assistance'
    WHEN naics_code LIKE '48%%' OR naics_code LIKE '49%%' THEN 'Transportation & Warehousing'
    WHEN naics_code LIKE '56%%' THEN 'Admin & Staffing Services'
    ELSE 'All Other'
END
"""


def _build_where(
    filters: dict[str, Any],
) -> tuple[str, list[Any]]:
    """Build WHERE clause from insight filters."""
    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("naics_prefix"):
        conditions.append("naics_code LIKE %s")
        params.append(f"{filters['naics_prefix']}%")

    if filters.get("state"):
        conditions.append("recipient_state_code = %s")
        params.append(filters["state"])

    if filters.get("business_size"):
        conditions.append("contracting_officers_determination_of_business_size = %s")
        params.append(filters["business_size"])

    if filters.get("awarding_agency_code"):
        conditions.append("awarding_agency_code = %s")
        params.append(filters["awarding_agency_code"])

    if filters.get("action_date_from"):
        conditions.append("action_date::DATE >= %s::DATE")
        params.append(filters["action_date_from"])

    if filters.get("action_date_to"):
        conditions.append("action_date::DATE <= %s::DATE")
        params.append(filters["action_date_to"])

    if filters.get("awardee_type") == "first_time":
        conditions.append("is_first_time_awardee = TRUE")
    elif filters.get("awardee_type") == "repeat":
        conditions.append("is_first_time_awardee = FALSE")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    return where_clause, params


# ── Function 1: Vertical Insights ──────────────────────────────────────────


def get_vertical_insights(
    *,
    filters: dict[str, Any] | None = None,
    group_by: str = "vertical",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Flexible vertical/sub-NAICS breakdown with date and awardee-type filters.

    group_by:
        "vertical" — 7-bucket NAICS vertical labels
        "naics_code" — individual NAICS codes (use with naics_prefix to drill into a vertical)

    filters:
        naics_prefix, state, business_size, awarding_agency_code,
        action_date_from, action_date_to (YYYY-MM-DD),
        awardee_type ("first_time" | "repeat" | None for all)
    """
    filters = filters or {}
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    where_clause, params = _build_where(filters)

    if group_by == "naics_code":
        group_expr = "naics_code"
        select_label = "naics_code"
        extra_select = "MAX(naics_description) AS naics_description,"
    else:
        group_expr = f"{VERTICAL_CASE}"
        select_label = "vertical"
        extra_select = ""

    sql = f"""
        SELECT
            {group_expr} AS {select_label},
            {extra_select}
            COUNT(DISTINCT recipient_uei) AS total_companies,
            COUNT(DISTINCT contract_award_unique_key) AS total_awards,
            COUNT(*) AS total_transactions,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT contract_award_unique_key), 0) AS avg_award_value,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)
            ) AS median_award_value,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_companies,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = FALSE) AS repeat_companies,
            COUNT(DISTINCT contract_award_unique_key) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awards,
            COUNT(DISTINCT contract_award_unique_key) FILTER (WHERE is_first_time_awardee = FALSE) AS repeat_awards,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))
                FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_total_obligated,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))
                FILTER (WHERE is_first_time_awardee = FALSE) AS repeat_total_obligated,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = TRUE)
                / NULLIF(COUNT(DISTINCT contract_award_unique_key) FILTER (WHERE is_first_time_awardee = TRUE), 0)
                AS first_time_avg_award_value,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = FALSE)
                / NULLIF(COUNT(DISTINCT contract_award_unique_key) FILTER (WHERE is_first_time_awardee = FALSE), 0)
                AS repeat_avg_award_value,
            COUNT(*) OVER() AS total_matched
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY {select_label}
        ORDER BY SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) DESC
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
        item: dict[str, Any] = {}
        if group_by == "naics_code":
            item["naics_code"] = row["naics_code"]
            item["naics_description"] = row["naics_description"]
        else:
            item["vertical"] = row["vertical"]

        item.update({
            "total_companies": row["total_companies"],
            "total_awards": row["total_awards"],
            "total_transactions": row["total_transactions"],
            "total_obligated": _float(row["total_obligated"]),
            "avg_award_value": _float(row["avg_award_value"]),
            "median_award_value": _float(row["median_award_value"]),
            "first_time_companies": row["first_time_companies"],
            "repeat_companies": row["repeat_companies"],
            "first_time_awards": row["first_time_awards"],
            "repeat_awards": row["repeat_awards"],
            "first_time_total_obligated": _float(row["first_time_total_obligated"]),
            "repeat_total_obligated": _float(row["repeat_total_obligated"]),
            "first_time_avg_award_value": _float(row["first_time_avg_award_value"]),
            "repeat_avg_award_value": _float(row["repeat_avg_award_value"]),
        })
        items.append(item)

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }


# ── Function 2: Agency Insights ────────────────────────────────────────────


def get_agency_insights(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Breakdown by awarding agency with first-time/repeat splits and date filters.

    filters:
        naics_prefix, state, business_size,
        action_date_from, action_date_to,
        awardee_type ("first_time" | "repeat" | None)
    """
    filters = filters or {}
    where_clause, params = _build_where(filters)

    sql = f"""
        SELECT
            awarding_agency_code,
            MAX(awarding_agency_name) AS awarding_agency_name,
            COUNT(DISTINCT recipient_uei) AS total_companies,
            COUNT(DISTINCT contract_award_unique_key) AS total_awards,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT contract_award_unique_key), 0) AS avg_award_value,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_companies,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = FALSE) AS repeat_companies,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = TRUE)
                / NULLIF(COUNT(DISTINCT contract_award_unique_key) FILTER (WHERE is_first_time_awardee = TRUE), 0)
                AS first_time_avg_award_value,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = FALSE)
                / NULLIF(COUNT(DISTINCT contract_award_unique_key) FILTER (WHERE is_first_time_awardee = FALSE), 0)
                AS repeat_avg_award_value
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY awarding_agency_code
        ORDER BY SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "awarding_agency_code": row["awarding_agency_code"],
            "awarding_agency_name": row["awarding_agency_name"],
            "total_companies": row["total_companies"],
            "total_awards": row["total_awards"],
            "total_obligated": _float(row["total_obligated"]),
            "avg_award_value": _float(row["avg_award_value"]),
            "first_time_companies": row["first_time_companies"],
            "repeat_companies": row["repeat_companies"],
            "first_time_avg_award_value": _float(row["first_time_avg_award_value"]),
            "repeat_avg_award_value": _float(row["repeat_avg_award_value"]),
        }
        for row in rows
    ]


# ── Function 3: Repeat Awardee Cumulative Summary ──────────────────────────


def get_repeat_awardee_cumulative(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Average cumulative total obligated per repeat awardee company, by vertical.

    Deduplicates to one row per (vertical, company) using the denormalized
    total_awards_count field, then averages per vertical.

    filters: naics_prefix, state, business_size, awarding_agency_code,
             action_date_from, action_date_to
    """
    filters = filters or {}
    # Build WHERE — always filter to repeat awardees
    base_filters = {**filters, "awardee_type": "repeat"}
    where_clause, params = _build_where(base_filters)

    sql = f"""
        WITH per_company AS (
            SELECT
                {VERTICAL_CASE} AS vertical,
                recipient_uei,
                SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS company_total_obligated,
                COUNT(DISTINCT contract_award_unique_key) AS company_award_count,
                MAX(CAST(NULLIF(total_awards_count, '') AS INTEGER)) AS total_awards_count_max
            FROM entities.mv_federal_contract_leads
            {where_clause}
            GROUP BY vertical, recipient_uei
        )
        SELECT
            vertical,
            COUNT(*) AS repeat_companies,
            AVG(company_total_obligated) AS avg_cumulative_obligated,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY company_total_obligated) AS median_cumulative_obligated,
            AVG(company_award_count) AS avg_awards_per_company,
            AVG(total_awards_count_max) AS avg_total_awards_count,
            SUM(company_total_obligated) AS total_obligated
        FROM per_company
        GROUP BY vertical
        ORDER BY AVG(company_total_obligated) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "vertical": row["vertical"],
            "repeat_companies": row["repeat_companies"],
            "avg_cumulative_obligated": _float(row["avg_cumulative_obligated"]),
            "median_cumulative_obligated": _float(row["median_cumulative_obligated"]),
            "avg_awards_per_company": _float(row["avg_awards_per_company"]),
            "avg_total_awards_count": _float(row["avg_total_awards_count"]),
            "total_obligated": _float(row["total_obligated"]),
        }
        for row in rows
    ]
