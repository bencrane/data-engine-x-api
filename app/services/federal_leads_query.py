"""Federal Contract Leads — query service against the materialized view."""
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


def query_federal_contract_leads(
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
        conditions.append("naics_code LIKE %s")
        params.append(f"{filters['naics_prefix']}%")

    if filters.get("state"):
        conditions.append("recipient_state_code = %s")
        params.append(filters["state"])

    if filters.get("action_date_from"):
        conditions.append("action_date >= %s")
        params.append(filters["action_date_from"])

    if filters.get("action_date_to"):
        conditions.append("action_date <= %s")
        params.append(filters["action_date_to"])

    if filters.get("min_obligation"):
        conditions.append("CAST(federal_action_obligation AS NUMERIC) >= %s")
        params.append(float(filters["min_obligation"]))

    if filters.get("business_size"):
        conditions.append("contracting_officers_determination_of_business_size = %s")
        params.append(filters["business_size"])

    if filters.get("first_time_only"):
        conditions.append("is_first_time_awardee = TRUE")

    if filters.get("awarding_agency_code"):
        conditions.append("awarding_agency_code = %s")
        params.append(filters["awarding_agency_code"])

    if filters.get("has_sam_match"):
        conditions.append("has_sam_match = TRUE")

    if filters.get("recipient_uei"):
        conditions.append("recipient_uei = %s")
        params.append(filters["recipient_uei"])

    if filters.get("recipient_name"):
        conditions.append("recipient_name ILIKE %s")
        params.append(f"%{filters['recipient_name']}%")

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_matched
        FROM entities.mv_federal_contract_leads
        {where_clause}
        ORDER BY action_date DESC
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
