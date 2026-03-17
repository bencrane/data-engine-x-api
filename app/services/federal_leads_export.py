"""Federal Contract Leads — CSV export with streaming cursor."""
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
    """Build WHERE clause using the same filter logic as query_federal_contract_leads."""
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

    if filters.get("first_time_dod_only"):
        conditions.append("is_first_time_dod_awardee = TRUE AND dod_awards_count > 0")

    if filters.get("first_time_nasa_only"):
        conditions.append("is_first_time_nasa_awardee = TRUE AND nasa_awards_count > 0")

    if filters.get("first_time_doe_only"):
        conditions.append("is_first_time_doe_awardee = TRUE AND doe_awards_count > 0")

    if filters.get("first_time_dhs_only"):
        conditions.append("is_first_time_dhs_awardee = TRUE AND dhs_awards_count > 0")

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

    return where_clause, params


def stream_federal_contract_leads_csv(
    *,
    filters: dict[str, Any],
    max_rows: int = 100_000,
) -> Iterator[str]:
    """Yield CSV lines for all matching federal contract leads rows.

    Uses a server-side cursor to avoid loading all rows into memory.
    Raises ValueError if the result set exceeds max_rows.
    """
    where_clause, params = _build_where(filters)

    # First, check the count
    count_sql = f"""
        SELECT COUNT(*)
        FROM entities.mv_federal_contract_leads
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
        FROM entities.mv_federal_contract_leads
        {where_clause}
        ORDER BY action_date DESC
    """

    with pool.connection() as conn:
        with conn.cursor(name="csv_export_cursor") as cur:
            cur.itersize = 5000
            cur.execute(data_sql, params)

            # Get column names from cursor description
            columns = [desc[0] for desc in cur.description]

            # Yield header row
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(columns)
            yield buf.getvalue()

            # Yield data rows in chunks
            while True:
                rows = cur.fetchmany(5000)
                if not rows:
                    break
                for row in rows:
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(row)
                    yield buf.getvalue()
