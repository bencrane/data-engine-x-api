"""Federal Contract Leads — time series, distribution, and velocity analytics."""
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


def _build_analytics_where(
    filters: dict[str, Any] | None,
    *,
    include_state: bool = True,
) -> tuple[str, list[Any]]:
    """Build WHERE clause from the standard analytics filter set."""
    filters = filters or {}
    conditions: list[str] = []
    params: list[Any] = []

    if filters.get("naics_prefix"):
        conditions.append("naics_code LIKE %s")
        params.append(f"{filters['naics_prefix']}%")

    if include_state and filters.get("state"):
        conditions.append("recipient_state_code = %s")
        params.append(filters["state"])

    if filters.get("business_size"):
        conditions.append("contracting_officers_determination_of_business_size = %s")
        params.append(filters["business_size"])

    if filters.get("awarding_agency_code"):
        conditions.append("awarding_agency_code = %s")
        params.append(filters["awarding_agency_code"])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)
    return where_clause, params


# ── Function 1: Time Series ──────────────────────────────────────────────────


def get_time_series(
    *,
    period: str = "quarter",
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group metrics by time period (month or quarter)."""
    if period == "month":
        bucket_expr = "TO_CHAR(action_date::DATE, 'YYYY-MM')"
    else:
        bucket_expr = "TO_CHAR(action_date::DATE, 'YYYY-\"Q\"Q')"

    where_clause, params = _build_analytics_where(filters)

    sql = f"""
        SELECT
            {bucket_expr} AS period,
            COUNT(DISTINCT recipient_uei) AS total_companies,
            COUNT(DISTINCT contract_award_unique_key) AS total_awards,
            COUNT(*) AS total_transactions,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awardee_companies
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY {bucket_expr}
        ORDER BY {bucket_expr} ASC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "period": row["period"],
            "total_companies": row["total_companies"],
            "total_awards": row["total_awards"],
            "total_transactions": row["total_transactions"],
            "total_obligated": _float(row["total_obligated"]),
            "average_award_value": _float(row["total_obligated"]) / row["total_awards"] if row["total_awards"] else 0.0,
            "first_time_awardee_companies": row["first_time_awardee_companies"],
            "repeat_awardee_companies": row["total_companies"] - row["first_time_awardee_companies"],
            "new_entrant_pct": round(
                row["first_time_awardee_companies"] / row["total_companies"] * 100, 2
            ) if row["total_companies"] else 0.0,
        }
        for row in rows
    ]


# ── Function 2: Award Size Distribution ──────────────────────────────────────


def get_award_size_distribution(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group by NAICS vertical and award size bucket."""
    where_clause, params = _build_analytics_where(filters)

    sql = f"""
        SELECT
            {VERTICAL_CASE} AS vertical,
            CASE
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 100000 THEN 'Under $100K'
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 500000 THEN '$100K-$500K'
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 1000000 THEN '$500K-$1M'
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 5000000 THEN '$1M-$5M'
                ELSE '$5M+'
            END AS size_bucket,
            CASE
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 100000 THEN 1
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 500000 THEN 2
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 1000000 THEN 3
                WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 5000000 THEN 4
                ELSE 5
            END AS bucket_order,
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT recipient_uei) AS unique_companies,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY {VERTICAL_CASE}), 0) * 100 AS pct_of_vertical_transactions,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) /
                NULLIF(SUM(SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))) OVER (PARTITION BY {VERTICAL_CASE}), 0) * 100 AS pct_of_vertical_dollars
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY vertical, size_bucket, bucket_order
        ORDER BY vertical ASC, bucket_order ASC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "vertical": row["vertical"],
            "size_bucket": row["size_bucket"],
            "transaction_count": row["transaction_count"],
            "unique_companies": row["unique_companies"],
            "total_obligated": _float(row["total_obligated"]),
            "pct_of_vertical_transactions": _float(row["pct_of_vertical_transactions"]),
            "pct_of_vertical_dollars": _float(row["pct_of_vertical_dollars"]),
        }
        for row in rows
    ]


# ── Function 3: Set-Aside Breakdown ──────────────────────────────────────────


def get_set_aside_breakdown(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group by NAICS vertical and set-aside type."""
    where_clause, params = _build_analytics_where(filters)

    sql = f"""
        SELECT
            {VERTICAL_CASE} AS vertical,
            COALESCE(NULLIF(type_of_set_aside, ''), 'NONE') AS set_aside_type,
            COUNT(*) AS transaction_count,
            COUNT(DISTINCT recipient_uei) AS unique_companies,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY {VERTICAL_CASE}), 0) * 100 AS pct_of_vertical_transactions
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY vertical, set_aside_type
        ORDER BY vertical ASC, SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "vertical": row["vertical"],
            "set_aside_type": row["set_aside_type"],
            "transaction_count": row["transaction_count"],
            "unique_companies": row["unique_companies"],
            "total_obligated": _float(row["total_obligated"]),
            "pct_of_vertical_transactions": _float(row["pct_of_vertical_transactions"]),
        }
        for row in rows
    ]


# ── Function 4: Competition Metrics ──────────────────────────────────────────


def get_competition_metrics(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Group by NAICS vertical with competition analysis."""
    where_clause, params = _build_analytics_where(filters)

    sql = f"""
        SELECT
            {VERTICAL_CASE} AS vertical,
            COUNT(DISTINCT contract_award_unique_key) AS total_awards,
            AVG(CAST(NULLIF(number_of_offers_received, '') AS NUMERIC)) AS avg_offers_received,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(number_of_offers_received, '') AS NUMERIC)) AS median_offers_received,
            COUNT(*) FILTER (WHERE extent_competed IN (
                'NOT COMPETED UNDER SAP',
                'NOT AVAILABLE FOR COMPETITION',
                'NOT COMPETED'
            )) AS sole_source_count,
            COUNT(*) AS total_transactions,
            COUNT(*) FILTER (WHERE extent_competed = 'FULL AND OPEN COMPETITION') AS full_competition_count
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY vertical
        ORDER BY COUNT(DISTINCT contract_award_unique_key) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "vertical": row["vertical"],
            "total_awards": row["total_awards"],
            "avg_offers_received": _float(row["avg_offers_received"]),
            "median_offers_received": _float(row["median_offers_received"]),
            "sole_source_count": row["sole_source_count"],
            "sole_source_pct": round(
                row["sole_source_count"] / row["total_transactions"] * 100, 2
            ) if row["total_transactions"] else 0.0,
            "full_competition_count": row["full_competition_count"],
            "full_competition_pct": round(
                row["full_competition_count"] / row["total_transactions"] * 100, 2
            ) if row["total_transactions"] else 0.0,
        }
        for row in rows
    ]


# ── Function 5: Geographic Hotspots ──────────────────────────────────────────


def get_geographic_hotspots(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Per-state metrics. No state filter (state IS the dimension)."""
    where_clause, params = _build_analytics_where(filters, include_state=False)

    sql = f"""
        SELECT
            recipient_state_code AS state,
            COUNT(DISTINCT recipient_uei) AS total_companies,
            COUNT(DISTINCT contract_award_unique_key) AS total_awards,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awardee_companies
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY recipient_state_code
        ORDER BY SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "state": row["state"],
            "total_companies": row["total_companies"],
            "total_awards": row["total_awards"],
            "total_obligated": _float(row["total_obligated"]),
            "first_time_awardee_companies": row["first_time_awardee_companies"],
            "pct_first_time": round(
                row["first_time_awardee_companies"] / row["total_companies"] * 100, 2
            ) if row["total_companies"] else 0.0,
            "avg_award_value": _float(row["total_obligated"]) / row["total_awards"] if row["total_awards"] else 0.0,
        }
        for row in rows
    ]


# ── Function 6: Repeat Awardee Velocity ──────────────────────────────────────


def get_repeat_awardee_velocity(
    *,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Time gap between a company's first and second distinct award."""
    filters = filters or {}
    conditions = [
        "is_first_time_awardee = FALSE",
        "recipient_uei IS NOT NULL AND recipient_uei != ''",
        "action_date IS NOT NULL AND action_date != ''",
    ]
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

    where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        WITH company_awards AS (
            SELECT
                recipient_uei,
                contract_award_unique_key,
                MIN(action_date::DATE) AS award_date
            FROM entities.mv_federal_contract_leads
            {where_clause}
            GROUP BY recipient_uei, contract_award_unique_key
        ),
        ranked AS (
            SELECT
                recipient_uei,
                award_date,
                ROW_NUMBER() OVER (PARTITION BY recipient_uei ORDER BY award_date) AS award_rank
            FROM company_awards
        ),
        velocity AS (
            SELECT
                r1.recipient_uei,
                r1.award_date AS first_award_date,
                r2.award_date AS second_award_date,
                (r2.award_date - r1.award_date) AS days_between
            FROM ranked r1
            JOIN ranked r2 ON r1.recipient_uei = r2.recipient_uei
            WHERE r1.award_rank = 1 AND r2.award_rank = 2
        )
        SELECT
            COUNT(*) AS companies_measured,
            AVG(days_between)::NUMERIC AS avg_days_between,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_between) AS median_days_between,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY days_between) AS p25_days_between,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY days_between) AS p75_days_between,
            MIN(days_between) AS min_days_between,
            MAX(days_between) AS max_days_between,
            COUNT(*) FILTER (WHERE days_between <= 90) AS within_90_days,
            COUNT(*) FILTER (WHERE days_between BETWEEN 91 AND 180) AS within_91_180_days,
            COUNT(*) FILTER (WHERE days_between BETWEEN 181 AND 365) AS within_181_365_days,
            COUNT(*) FILTER (WHERE days_between > 365) AS over_365_days
        FROM velocity
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params, prepare=False)
            row = cur.fetchone()

    if not row or row["companies_measured"] == 0:
        return {
            "companies_measured": 0,
            "avg_days_between": 0.0,
            "median_days_between": 0.0,
            "p25_days_between": 0.0,
            "p75_days_between": 0.0,
            "min_days_between": 0,
            "max_days_between": 0,
            "distribution": {
                "within_90_days": 0,
                "within_91_180_days": 0,
                "within_181_365_days": 0,
                "over_365_days": 0,
            },
        }

    return {
        "companies_measured": row["companies_measured"],
        "avg_days_between": _float(row["avg_days_between"]),
        "median_days_between": _float(row["median_days_between"]),
        "p25_days_between": _float(row["p25_days_between"]),
        "p75_days_between": _float(row["p75_days_between"]),
        "min_days_between": int(row["min_days_between"]),
        "max_days_between": int(row["max_days_between"]),
        "distribution": {
            "within_90_days": row["within_90_days"],
            "within_91_180_days": row["within_91_180_days"],
            "within_181_365_days": row["within_181_365_days"],
            "over_365_days": row["over_365_days"],
        },
    }


# ── Function 7: Award Ceiling Gap ────────────────────────────────────────────


def get_award_ceiling_gap(
    *,
    filters: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Obligation vs ceiling per NAICS vertical — expansion runway."""
    where_clause, params = _build_analytics_where(filters)

    sql = f"""
        SELECT
            {VERTICAL_CASE} AS vertical,
            SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            SUM(CAST(NULLIF(potential_total_value_of_award, '') AS NUMERIC)) AS total_ceiling,
            COUNT(DISTINCT recipient_uei) AS unique_companies
        FROM entities.mv_federal_contract_leads
        {where_clause}
        GROUP BY vertical
        ORDER BY
            SUM(CAST(NULLIF(potential_total_value_of_award, '') AS NUMERIC))
            / NULLIF(SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)), 0) DESC
    """

    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        {
            "vertical": row["vertical"],
            "total_obligated": _float(row["total_obligated"]),
            "total_ceiling": _float(row["total_ceiling"]),
            "ceiling_to_obligation_ratio": round(
                _float(row["total_ceiling"]) / _float(row["total_obligated"]), 2
            ) if _float(row["total_obligated"]) != 0 else 0.0,
            "avg_obligation_per_company": round(
                _float(row["total_obligated"]) / row["unique_companies"], 2
            ) if row["unique_companies"] else 0.0,
            "avg_ceiling_per_company": round(
                _float(row["total_ceiling"]) / row["unique_companies"], 2
            ) if row["unique_companies"] else 0.0,
            "unique_companies": row["unique_companies"],
        }
        for row in rows
    ]
