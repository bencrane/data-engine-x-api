"""Federal Contract Leads — consolidated analytics with temporal first-time definition."""
from __future__ import annotations

import logging
import re
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


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_date(val: str, name: str) -> None:
    if not _DATE_RE.match(val):
        raise ValueError(f"{name} must be YYYY-MM-DD, got: {val!r}")


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

# Shared CTE: compute each company's earliest action_date across ALL data.
_COMPANY_FIRST_DATES_CTE = """
company_first_dates AS (
    SELECT
        recipient_uei,
        MIN(action_date::DATE) AS first_action_date
    FROM entities.mv_federal_contract_leads
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND action_date IS NOT NULL AND action_date != ''
    GROUP BY recipient_uei
)
"""

_QUERY_DISPATCH: dict[str, Any] = {}


def run_federal_analytics(
    *,
    query_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch to the appropriate analytics query function."""
    handler = _QUERY_DISPATCH.get(query_type)
    if handler is None:
        raise ValueError(f"Unknown query_type: {query_type!r}")
    return handler(params or {})


def _require_dates(p: dict[str, Any]) -> tuple[str, str]:
    date_from = p.get("date_from")
    date_to = p.get("date_to")
    if not date_from or not date_to:
        raise ValueError("date_from and date_to are required")
    _validate_date(date_from, "date_from")
    _validate_date(date_to, "date_to")
    return date_from, date_to


def _execute(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    pool = _get_pool()
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SET statement_timeout = '30s'")
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.execute("RESET statement_timeout")
    return rows


# ── Query Type 1: first_time_awardees_by_naics ─────────────────────────────


def _first_time_awardees_by_naics(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _require_dates(p)
    limit = min(max(int(p.get("limit", 20)), 1), 500)

    sql = f"""
        WITH {_COMPANY_FIRST_DATES_CTE},
        new_entrants AS (
            SELECT recipient_uei
            FROM company_first_dates
            WHERE first_action_date BETWEEN %s AND %s
        )
        SELECT
            {VERTICAL_CASE} AS vertical,
            COUNT(DISTINCT m.recipient_uei) AS first_time_companies,
            COUNT(DISTINCT m.contract_award_unique_key) AS first_time_awards,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS first_time_total_obligated,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) AS first_time_avg_award_value
        FROM entities.mv_federal_contract_leads m
        JOIN new_entrants ne ON m.recipient_uei = ne.recipient_uei
        WHERE m.action_date::DATE BETWEEN %s AND %s
        GROUP BY vertical
        ORDER BY COUNT(DISTINCT m.recipient_uei) DESC
        LIMIT %s
    """

    rows = _execute(sql, [date_from, date_to, date_from, date_to, limit])
    return {
        "query_type": "first_time_awardees_by_naics",
        "date_range": {"from": date_from, "to": date_to},
        "items": [
            {
                "vertical": r["vertical"],
                "first_time_companies": r["first_time_companies"],
                "first_time_awards": r["first_time_awards"],
                "first_time_total_obligated": _float(r["first_time_total_obligated"]),
                "first_time_avg_award_value": _float(r["first_time_avg_award_value"]),
            }
            for r in rows
        ],
    }


# ── Query Type 2: first_time_avg_award_by_naics ────────────────────────────


def _first_time_avg_award_by_naics(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _require_dates(p)
    limit = min(max(int(p.get("limit", 20)), 1), 500)

    sql = f"""
        WITH {_COMPANY_FIRST_DATES_CTE},
        new_entrants AS (
            SELECT recipient_uei
            FROM company_first_dates
            WHERE first_action_date BETWEEN %s AND %s
        )
        SELECT
            {VERTICAL_CASE} AS vertical,
            COUNT(DISTINCT m.recipient_uei) AS first_time_companies,
            COUNT(DISTINCT m.contract_award_unique_key) AS first_time_awards,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) AS first_time_avg_award_value,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)
            ) AS first_time_median_award_value,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS first_time_total_obligated
        FROM entities.mv_federal_contract_leads m
        JOIN new_entrants ne ON m.recipient_uei = ne.recipient_uei
        WHERE m.action_date::DATE BETWEEN %s AND %s
        GROUP BY vertical
        ORDER BY SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
            / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) DESC
        LIMIT %s
    """

    rows = _execute(sql, [date_from, date_to, date_from, date_to, limit])
    return {
        "query_type": "first_time_avg_award_by_naics",
        "date_range": {"from": date_from, "to": date_to},
        "items": [
            {
                "vertical": r["vertical"],
                "first_time_companies": r["first_time_companies"],
                "first_time_awards": r["first_time_awards"],
                "first_time_avg_award_value": _float(r["first_time_avg_award_value"]),
                "first_time_median_award_value": _float(r["first_time_median_award_value"]),
                "first_time_total_obligated": _float(r["first_time_total_obligated"]),
            }
            for r in rows
        ],
    }


# ── Query Type 3: total_by_naics ───────────────────────────────────────────


def _total_by_naics(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _require_dates(p)
    limit = min(max(int(p.get("limit", 20)), 1), 500)

    sql = f"""
        WITH {_COMPANY_FIRST_DATES_CTE},
        new_entrants AS (
            SELECT recipient_uei
            FROM company_first_dates
            WHERE first_action_date BETWEEN %s AND %s
        )
        SELECT
            {VERTICAL_CASE} AS vertical,
            COUNT(DISTINCT m.recipient_uei) AS total_companies,
            COUNT(DISTINCT m.contract_award_unique_key) AS total_awards,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) AS avg_award_value,
            COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NOT NULL) AS first_time_companies,
            COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NULL) AS repeat_companies,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                FILTER (WHERE ne.recipient_uei IS NOT NULL) AS first_time_total_obligated,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                FILTER (WHERE ne.recipient_uei IS NULL) AS repeat_total_obligated,
            COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NOT NULL)::NUMERIC
                / NULLIF(COUNT(DISTINCT m.recipient_uei), 0) * 100 AS first_time_pct
        FROM entities.mv_federal_contract_leads m
        LEFT JOIN new_entrants ne ON m.recipient_uei = ne.recipient_uei
        WHERE m.action_date::DATE BETWEEN %s AND %s
          AND m.recipient_uei IS NOT NULL AND m.recipient_uei != ''
        GROUP BY vertical
        ORDER BY SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) DESC
        LIMIT %s
    """

    rows = _execute(sql, [date_from, date_to, date_from, date_to, limit])
    return {
        "query_type": "total_by_naics",
        "date_range": {"from": date_from, "to": date_to},
        "items": [
            {
                "vertical": r["vertical"],
                "total_companies": r["total_companies"],
                "total_awards": r["total_awards"],
                "total_obligated": _float(r["total_obligated"]),
                "avg_award_value": _float(r["avg_award_value"]),
                "first_time_companies": r["first_time_companies"],
                "repeat_companies": r["repeat_companies"],
                "first_time_total_obligated": _float(r["first_time_total_obligated"]),
                "repeat_total_obligated": _float(r["repeat_total_obligated"]),
                "first_time_pct": _float(r["first_time_pct"]),
            }
            for r in rows
        ],
    }


# ── Query Type 4: sub_naics_breakdown ──────────────────────────────────────


def _sub_naics_breakdown(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _require_dates(p)
    naics_prefix = p.get("naics_prefix")
    if not naics_prefix:
        raise ValueError("naics_prefix is required for sub_naics_breakdown")
    limit = min(max(int(p.get("limit", 50)), 1), 500)

    sql = f"""
        WITH {_COMPANY_FIRST_DATES_CTE},
        new_entrants AS (
            SELECT recipient_uei
            FROM company_first_dates
            WHERE first_action_date BETWEEN %s AND %s
        )
        SELECT
            m.naics_code,
            MAX(m.naics_description) AS naics_description,
            COUNT(DISTINCT m.recipient_uei) AS total_companies,
            COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NOT NULL) AS first_time_companies,
            COUNT(DISTINCT m.contract_award_unique_key) AS total_awards,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                FILTER (WHERE ne.recipient_uei IS NOT NULL) AS first_time_total_obligated,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) AS avg_award_value,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                FILTER (WHERE ne.recipient_uei IS NOT NULL)
                / NULLIF(
                    COUNT(DISTINCT m.contract_award_unique_key)
                    FILTER (WHERE ne.recipient_uei IS NOT NULL), 0
                ) AS first_time_avg_award_value
        FROM entities.mv_federal_contract_leads m
        LEFT JOIN new_entrants ne ON m.recipient_uei = ne.recipient_uei
        WHERE m.action_date::DATE BETWEEN %s AND %s
          AND m.recipient_uei IS NOT NULL AND m.recipient_uei != ''
          AND m.naics_code LIKE %s
        GROUP BY m.naics_code
        ORDER BY COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NOT NULL) DESC
        LIMIT %s
    """

    rows = _execute(
        sql,
        [date_from, date_to, date_from, date_to, f"{naics_prefix}%", limit],
    )
    return {
        "query_type": "sub_naics_breakdown",
        "date_range": {"from": date_from, "to": date_to},
        "naics_prefix": naics_prefix,
        "items": [
            {
                "naics_code": r["naics_code"],
                "naics_description": r["naics_description"],
                "total_companies": r["total_companies"],
                "first_time_companies": r["first_time_companies"],
                "total_awards": r["total_awards"],
                "total_obligated": _float(r["total_obligated"]),
                "first_time_total_obligated": _float(r["first_time_total_obligated"]),
                "avg_award_value": _float(r["avg_award_value"]),
                "first_time_avg_award_value": _float(r["first_time_avg_award_value"]),
            }
            for r in rows
        ],
    }


# ── Query Type 5: first_time_by_agency ─────────────────────────────────────


def _first_time_by_agency(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _require_dates(p)
    limit = min(max(int(p.get("limit", 20)), 1), 500)

    sql = f"""
        WITH {_COMPANY_FIRST_DATES_CTE},
        new_entrants AS (
            SELECT recipient_uei
            FROM company_first_dates
            WHERE first_action_date BETWEEN %s AND %s
        )
        SELECT
            m.awarding_agency_code,
            MAX(m.awarding_agency_name) AS awarding_agency_name,
            COUNT(DISTINCT m.recipient_uei) AS first_time_companies,
            COUNT(DISTINCT m.contract_award_unique_key) AS first_time_awards,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS first_time_total_obligated,
            SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
                / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) AS first_time_avg_award_value,
            COUNT(DISTINCT m.recipient_uei)::NUMERIC
                / NULLIF(SUM(COUNT(DISTINCT m.recipient_uei)) OVER(), 0) * 100 AS pct_of_all_first_timers
        FROM entities.mv_federal_contract_leads m
        JOIN new_entrants ne ON m.recipient_uei = ne.recipient_uei
        WHERE m.action_date::DATE BETWEEN %s AND %s
        GROUP BY m.awarding_agency_code
        ORDER BY COUNT(DISTINCT m.recipient_uei) DESC
        LIMIT %s
    """

    rows = _execute(sql, [date_from, date_to, date_from, date_to, limit])
    return {
        "query_type": "first_time_by_agency",
        "date_range": {"from": date_from, "to": date_to},
        "items": [
            {
                "awarding_agency_code": r["awarding_agency_code"],
                "awarding_agency_name": r["awarding_agency_name"],
                "first_time_companies": r["first_time_companies"],
                "first_time_awards": r["first_time_awards"],
                "first_time_total_obligated": _float(r["first_time_total_obligated"]),
                "first_time_avg_award_value": _float(r["first_time_avg_award_value"]),
                "pct_of_all_first_timers": _float(r["pct_of_all_first_timers"]),
            }
            for r in rows
        ],
    }


# ── Query Type 6: repeat_awardee_avg_by_naics ─────────────────────────────


def _repeat_awardee_avg_by_naics(p: dict[str, Any]) -> dict[str, Any]:
    date_from, date_to = _require_dates(p)

    sql = f"""
        WITH {_COMPANY_FIRST_DATES_CTE},
        repeat_awardees AS (
            SELECT recipient_uei
            FROM company_first_dates
            WHERE first_action_date < %s
        ),
        per_company AS (
            SELECT
                {VERTICAL_CASE} AS vertical,
                m.recipient_uei,
                SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS company_total_obligated,
                COUNT(DISTINCT m.contract_award_unique_key) AS company_awards
            FROM entities.mv_federal_contract_leads m
            JOIN repeat_awardees ra ON m.recipient_uei = ra.recipient_uei
            WHERE m.action_date::DATE BETWEEN %s AND %s
            GROUP BY vertical, m.recipient_uei
        )
        SELECT
            vertical,
            COUNT(*) AS repeat_companies,
            AVG(company_total_obligated) AS avg_cumulative_obligated,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY company_total_obligated) AS median_cumulative_obligated,
            AVG(company_awards) AS avg_awards_per_company,
            SUM(company_total_obligated) AS total_obligated
        FROM per_company
        GROUP BY vertical
        ORDER BY AVG(company_total_obligated) DESC
    """

    rows = _execute(sql, [date_from, date_from, date_to])
    return {
        "query_type": "repeat_awardee_avg_by_naics",
        "date_range": {"from": date_from, "to": date_to},
        "items": [
            {
                "vertical": r["vertical"],
                "repeat_companies": r["repeat_companies"],
                "avg_cumulative_obligated": _float(r["avg_cumulative_obligated"]),
                "median_cumulative_obligated": _float(r["median_cumulative_obligated"]),
                "avg_awards_per_company": _float(r["avg_awards_per_company"]),
                "total_obligated": _float(r["total_obligated"]),
            }
            for r in rows
        ],
    }


# ── Dispatch registration ──────────────────────────────────────────────────

_QUERY_DISPATCH.update({
    "first_time_awardees_by_naics": _first_time_awardees_by_naics,
    "first_time_avg_award_by_naics": _first_time_avg_award_by_naics,
    "total_by_naics": _total_by_naics,
    "sub_naics_breakdown": _sub_naics_breakdown,
    "first_time_by_agency": _first_time_by_agency,
    "repeat_awardee_avg_by_naics": _repeat_awardee_avg_by_naics,
})
