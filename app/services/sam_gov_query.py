"""SAM.gov Entity Query — search, detail, and stats against typed materialized views."""
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
# search_sam_entities
# ---------------------------------------------------------------------------

def search_sam_entities(
    *,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    conditions: list[str] = []
    params: list[Any] = []

    # mv_sam_gov_entities_typed aliases physical_address_province_or_state → physical_state
    if filters.get("state"):
        conditions.append("physical_state = %s")
        params.append(filters["state"])

    if filters.get("naics_code"):
        conditions.append("primary_naics = %s")
        params.append(filters["naics_code"])

    if filters.get("naics_prefix"):
        conditions.append("primary_naics LIKE %s")
        params.append(f"{filters['naics_prefix']}%")

    if filters.get("registration_status"):
        conditions.append("sam_extract_code = %s")
        params.append(filters["registration_status"])

    if filters.get("entity_name"):
        conditions.append("legal_business_name ILIKE %s")
        params.append(f"%{filters['entity_name']}%")

    if filters.get("uei"):
        conditions.append("unique_entity_id = %s")
        params.append(filters["uei"])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT *, COUNT(*) OVER() AS total_matched
        FROM entities.mv_sam_gov_entities_typed
        {where_clause}
        ORDER BY legal_business_name ASC
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
# get_sam_entity_detail
# ---------------------------------------------------------------------------

def get_sam_entity_detail(*, uei: str) -> dict[str, Any] | None:
    pool = _get_pool()

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM entities.mv_sam_gov_entities_typed WHERE unique_entity_id = %s",
                [uei],
            )
            entity_row = cur.fetchone()

    if entity_row is None:
        return None

    entity = dict(entity_row)

    # Contract history from bridge MV (migration 042 — may not be deployed)
    contract_history = None
    try:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM entities.mv_sam_usaspending_bridge WHERE unique_entity_id = %s",
                    [uei],
                )
                bridge_row = cur.fetchone()
                if bridge_row:
                    contract_history = dict(bridge_row)
    except Exception:
        logger.debug("mv_sam_usaspending_bridge not available, skipping contract history")

    return {
        "entity": entity,
        "contract_history": contract_history,
    }


# ---------------------------------------------------------------------------
# get_sam_entity_stats
# ---------------------------------------------------------------------------

def get_sam_entity_stats(*, filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    pool = _get_pool()

    state_filter = filters.get("state")
    base_where = ""
    base_params: list[Any] = []
    if state_filter:
        base_where = "WHERE physical_state = %s"
        base_params = [state_filter]

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Total entities
            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM entities.mv_sam_gov_entities_typed {base_where}",
                base_params,
            )
            total_entities = cur.fetchone()["cnt"]

            # Entities by state (top 25)
            cur.execute(
                f"""
                SELECT physical_state AS state, COUNT(*) AS count
                FROM entities.mv_sam_gov_entities_typed
                {base_where}
                GROUP BY physical_state
                ORDER BY COUNT(*) DESC
                LIMIT 25
                """,
                base_params,
            )
            entities_by_state = [dict(r) for r in cur.fetchall()]

            # Entities by NAICS sector (top 20)
            cur.execute(
                f"""
                SELECT naics_sector, COUNT(*) AS count
                FROM entities.mv_sam_gov_entities_typed
                {("WHERE naics_sector IS NOT NULL" + (" AND physical_state = %s" if state_filter else "")) if True else ""}
                GROUP BY naics_sector
                ORDER BY COUNT(*) DESC
                LIMIT 20
                """,
                [state_filter] if state_filter else [],
            )
            entities_by_naics_sector = [dict(r) for r in cur.fetchall()]

            # Active vs expired
            cur.execute(
                f"""
                SELECT sam_extract_code, COUNT(*) AS count
                FROM entities.mv_sam_gov_entities_typed
                {base_where}
                GROUP BY sam_extract_code
                """,
                base_params,
            )
            status_rows = {r["sam_extract_code"]: r["count"] for r in cur.fetchall()}

    return {
        "total_entities": total_entities,
        "entities_by_state": entities_by_state,
        "entities_by_naics_sector": entities_by_naics_sector,
        "by_status": {
            "active": status_rows.get("A", 0),
            "expired": status_rows.get("E", 0),
        },
    }
