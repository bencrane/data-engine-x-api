"""Federal Leads — company detail aggregating SAM.gov, USASpending, and SBA data by UEI."""
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

# Common business name suffixes to strip for fuzzy matching
_STRIP_SUFFIXES = re.compile(
    r"\b(INC|LLC|CORP|CORPORATION|CO|LTD|LP|GROUP|COMPANY|ENTERPRISES|SERVICES|SOLUTIONS)\b",
    re.IGNORECASE,
)


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


def _extract_search_name(raw_name: str) -> str | None:
    """Strip common suffixes and noise words, return the core search term."""
    cleaned = _STRIP_SUFFIXES.sub("", raw_name)
    # Remove articles and noise
    cleaned = re.sub(r"\b(THE|OF|AND|A)\b", "", cleaned, flags=re.IGNORECASE)
    # Remove punctuation and collapse whitespace
    cleaned = re.sub(r"[^A-Za-z0-9 ]", "", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    # Use the longest remaining word as the search term
    words = cleaned.split()
    if not words:
        return None
    return max(words, key=len)


def get_company_detail(*, uei: str) -> dict[str, Any] | None:
    """Aggregate SAM.gov, USASpending, and SBA data for a single UEI."""
    pool = _get_pool()

    sam_registration = None
    company_name = None
    state_code = None

    # 1. SAM.gov registration
    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM entities.sam_gov_entities
                WHERE unique_entity_id = %s
                ORDER BY extract_date DESC
                LIMIT 1
                """,
                [uei],
            )
            row = cur.fetchone()
            if row:
                sam_registration = dict(row)
                company_name = sam_registration.get("legal_business_name")
                state_code = sam_registration.get("physical_address_province_or_state")

    # 2. USASpending awards
    awards_items: list[dict[str, Any]] = []
    awards_summary: dict[str, Any] = {
        "total_awards": 0,
        "total_obligated": 0.0,
        "earliest_action_date": None,
        "latest_action_date": None,
    }

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (contract_transaction_unique_key)
                    contract_award_unique_key,
                    award_type,
                    action_date,
                    federal_action_obligation,
                    total_dollars_obligated,
                    potential_total_value_of_award,
                    awarding_agency_name,
                    naics_code,
                    naics_description,
                    usaspending_permalink,
                    recipient_name,
                    recipient_state_code
                FROM entities.usaspending_contracts
                WHERE recipient_uei = %s
                ORDER BY contract_transaction_unique_key, extract_date DESC
                """,
                [uei],
            )
            usa_rows = cur.fetchall()

    if usa_rows:
        # Sort by action_date DESC for display
        awards_items = sorted(usa_rows, key=lambda r: r.get("action_date") or "", reverse=True)

        # If no SAM data, get company name/state from USASpending
        if not company_name:
            company_name = usa_rows[0].get("recipient_name")
        if not state_code:
            state_code = usa_rows[0].get("recipient_state_code")

        # Summary stats
        unique_awards = set()
        total_obligated = 0.0
        dates = []
        for r in usa_rows:
            if r.get("contract_award_unique_key"):
                unique_awards.add(r["contract_award_unique_key"])
            try:
                total_obligated += float(r.get("federal_action_obligation") or 0)
            except (ValueError, TypeError):
                pass
            if r.get("action_date"):
                dates.append(r["action_date"])

        awards_summary = {
            "total_awards": len(unique_awards),
            "total_obligated": round(total_obligated, 2),
            "earliest_action_date": min(dates) if dates else None,
            "latest_action_date": max(dates) if dates else None,
        }

    if not sam_registration and not usa_rows:
        return None

    # 3. SBA loans (fuzzy match)
    sba_items: list[dict[str, Any]] = []
    search_name = None
    search_state = state_code

    if company_name and state_code:
        search_name = _extract_search_name(company_name)

    sba_section: dict[str, Any] = {
        "items": [],
        "match_method": "fuzzy_name_state",
        "search_name": search_name,
        "search_state": search_state,
    }

    if search_name and search_state:
        with pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM entities.sba_7a_loans
                    WHERE borrstate = %s AND borrname ILIKE %s
                    ORDER BY approvaldate DESC
                    LIMIT 50
                    """,
                    [search_state, f"%{search_name}%"],
                )
                sba_items = [dict(r) for r in cur.fetchall()]

    sba_section["items"] = sba_items

    return {
        "uei": uei,
        "sam_registration": sam_registration,
        "awards": {
            "items": awards_items,
            **awards_summary,
        },
        "sba_loans": sba_section,
    }
