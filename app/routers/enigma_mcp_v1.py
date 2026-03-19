"""Enigma MCP proxy router — POST /call, GET /tools.

Proxies Enigma MCP business intelligence tools through data-engine-x with
auth, audit logging, credit guard, and opt-in persistence.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.providers.enigma_mcp import (
    BLOCKED_TOOLS,
    McpCallError,
    McpError,
    McpInsufficientCreditsError,
    McpRateLimitError,
    McpToolBlockedError,
    call_tool,
    list_tools,
)
from app.routers._responses import error_response
from app.services.enigma_mcp_persistence import persist_mcp_result
from app.services.operation_history import persist_operation_execution

router = APIRouter(prefix="/api/v1/enigma-mcp", tags=["enigma-mcp"])

# ---------------------------------------------------------------------------
# Auth — same pattern as execute_v1.py
# ---------------------------------------------------------------------------

_security = HTTPBearer(auto_error=False)


async def _resolve_flexible_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthContext | SuperAdminContext:
    """Accept super-admin API key or tenant auth (JWT / API token)."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    try:
        return await get_current_super_admin(credentials)
    except HTTPException:
        pass
    return await get_current_auth(request=request, credentials=credentials)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class McpCallRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = {}
    persist: bool = False
    max_results: int | None = None
    org_id: str | None = None  # Super-admin override
    company_id: str | None = None  # Super-admin override


class McpCallResponse(BaseModel):
    tool: str
    results: Any | None = None  # Structured JSON results (if parseable)
    raw_text: str | None = None  # Raw narrative text (if not JSON)
    result_count: int | None = None
    persisted: bool = False
    persisted_count: int | None = None
    persistence_status: dict[str, Any] | None = None
    credits_note: str | None = None


class McpToolListResponse(BaseModel):
    tools: list[dict[str, Any]]
    tool_count: int
    blocked_tools: list[str]


# ---------------------------------------------------------------------------
# Credit estimator
# ---------------------------------------------------------------------------


def _estimate_credits(
    tool_name: str, arguments: dict[str, Any], result_count: int | None
) -> str:
    limit = arguments.get("limit", 10)
    n = result_count or limit

    estimates = {
        "generate_locations_segment": f"~{n} credits (1 per location, Core tier)",
        "generate_brands_segment": f"~{n} credits (1 per brand, Core tier)",
        "search_business": "~1-3 credits (Core tier per result)",
        "get_brand_locations": f"~{n + 1} credits (1 brand + {n} locations)",
        "get_brand_card_analytics": "~4 credits (1 brand + Plus tier analytics)",
        "get_brand_legal_entities": "~6 credits (1 brand + Premium tier legal entities)",
        "get_brands_by_legal_entity": "~1-5 credits (depends on brand count)",
        "search_kyb": "KYB billing (separate from GraphQL credits)",
        "search_negative_news": "AI research credits (check Enigma billing)",
        "search_gov_archive": f"~{n} credits (depends on result count)",
    }
    return estimates.get(tool_name, "Credit cost unknown — check Enigma billing")


# ---------------------------------------------------------------------------
# POST /call
# ---------------------------------------------------------------------------


@router.post(
    "/call",
    response_model=McpCallResponse,
)
async def call_mcp_tool(
    payload: McpCallRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    # Resolve auth: super-admin requires org_id + company_id
    if isinstance(auth, SuperAdminContext):
        if not payload.org_id:
            return error_response("org_id is required for super-admin MCP calls", 400)
        if not payload.company_id:
            return error_response("company_id is required for super-admin MCP calls", 400)
        auth = AuthContext(
            user_id=None,
            org_id=payload.org_id,
            company_id=payload.company_id,
            role="org_admin",
            auth_method="api_token",
        )

    api_key = os.environ.get("ENIGMA_API_KEY")
    if not api_key:
        return error_response("ENIGMA_API_KEY not configured", 500)

    # Call tool
    try:
        mcp_result = await call_tool(
            api_key=api_key,
            tool_name=payload.tool,
            arguments=payload.arguments,
            max_results=payload.max_results,
        )
    except McpToolBlockedError as exc:
        return error_response(str(exc), 400)
    except McpRateLimitError:
        return error_response("Enigma MCP rate limit hit. Retry later.", 429)
    except McpInsufficientCreditsError:
        return error_response("Enigma insufficient credits.", 402)
    except McpError as exc:
        return error_response(f"Enigma MCP error: {exc}", 502)

    # Audit log (D7)
    run_id = str(uuid4())
    result_for_audit = {
        "status": "found" if mcp_result["is_structured"] or mcp_result["raw_text"] else "not_found",
        "output": mcp_result["parsed_result"] or {"raw_text": mcp_result["raw_text"]},
        "run_id": run_id,
        "operation_id": f"mcp.{payload.tool}",
    }
    persist_operation_execution(
        auth=auth,
        entity_type="company",
        operation_id=f"mcp.{payload.tool}",
        input_payload=payload.arguments,
        result=result_for_audit,
    )

    # Persistence (D4 — opt-in)
    persistence_status = None
    persisted_count = None
    if payload.persist and mcp_result["is_structured"]:
        persistence_status = persist_mcp_result(
            org_id=auth.org_id,
            company_id=auth.company_id,
            tool_name=payload.tool,
            parsed_result=mcp_result["parsed_result"],
            arguments=payload.arguments,
        )
        if persistence_status.get("status") == "succeeded":
            persisted_count = persistence_status.get("count")

    # Build response
    results = mcp_result["parsed_result"]
    result_count = None
    if isinstance(results, list):
        result_count = len(results)
    elif isinstance(results, dict):
        result_count = 1

    credits_note = _estimate_credits(payload.tool, payload.arguments, result_count)

    return McpCallResponse(
        tool=payload.tool,
        results=results,
        raw_text=mcp_result["raw_text"],
        result_count=result_count,
        persisted=persistence_status is not None
        and persistence_status.get("status") == "succeeded",
        persisted_count=persisted_count,
        persistence_status=persistence_status,
        credits_note=credits_note,
    )


# ---------------------------------------------------------------------------
# GET /tools
# ---------------------------------------------------------------------------


@router.get("/tools", response_model=McpToolListResponse)
async def list_mcp_tools(
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    force_refresh: bool = False,
):
    api_key = os.environ.get("ENIGMA_API_KEY")
    if not api_key:
        return error_response("ENIGMA_API_KEY not configured", 500)

    try:
        tools = await list_tools(api_key=api_key, force_refresh=force_refresh)
    except McpError as exc:
        return error_response(f"Failed to list MCP tools: {exc}", 502)

    return McpToolListResponse(
        tools=tools,
        tool_count=len(tools),
        blocked_tools=sorted(BLOCKED_TOOLS),
    )
