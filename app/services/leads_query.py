"""Leads query service — joins person + relationship + company into flat lead records."""
from __future__ import annotations

from typing import Any

from app.database import get_supabase_client


def query_leads(
    *,
    org_id: str,
    filters: dict[str, Any],
    limit: int = 25,
    offset: int = 0,
) -> dict[str, Any]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    rpc_params: dict[str, Any] = {
        "p_org_id": org_id,
        "p_limit": safe_limit,
        "p_offset": safe_offset,
    }

    # Map filter keys to RPC parameter names
    filter_map = {
        "industry": "p_industry",
        "employee_range": "p_employee_range",
        "hq_country": "p_hq_country",
        "canonical_domain": "p_canonical_domain",
        "company_name": "p_company_name",
        "title": "p_title",
        "seniority": "p_seniority",
        "department": "p_department",
        "email_status": "p_email_status",
        "has_email": "p_has_email",
        "has_phone": "p_has_phone",
    }

    for filter_key, param_name in filter_map.items():
        value = filters.get(filter_key)
        if value is not None:
            rpc_params[param_name] = value

    client = get_supabase_client()
    result = client.schema("entities").rpc("query_leads", rpc_params).execute()
    rows = result.data or []

    # Extract total_matched from the window function in the first row
    total_matched = 0
    items = []
    for row in rows:
        if isinstance(row, dict):
            total_matched = row.pop("total_matched", 0)
            items.append(row)
        else:
            # RPC returned JSON objects directly
            items.append(row)

    if not items:
        total_matched = 0

    return {
        "items": items,
        "total_matched": total_matched,
        "limit": safe_limit,
        "offset": safe_offset,
    }
