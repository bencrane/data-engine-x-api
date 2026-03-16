from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.contracts.intent_search import IntentSearchOutput, IntentSearchRequest
from app.routers._responses import DataEnvelope
from app.services.enum_registry.field_mappings import FIELD_REGISTRY
from app.services.intent_search import execute_intent_search

router = APIRouter()
_security = HTTPBearer(auto_error=False)

# Pass-through fields available per entity type
_TEXT_FILTERS: dict[str, dict[str, list[str]]] = {
    "companies": ["query", "company_domain", "company_name", "location"],
    "people": ["query", "company_domain", "company_name", "company_linkedin_url", "job_title", "location"],
}


async def _resolve_flexible_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthContext | SuperAdminContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    try:
        return await get_current_super_admin(credentials)
    except HTTPException:
        pass
    return await get_current_auth(request=request, credentials=credentials)


@router.get("/search/filters")
async def search_filters(
    provider: str = "prospeo",
    entity_type: str = "companies",
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    if provider not in ("prospeo", "blitzapi"):
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    if entity_type not in ("companies", "people"):
        raise HTTPException(status_code=400, detail=f"Unknown entity_type: {entity_type}")

    filters: dict[str, dict] = {}

    # Enum fields from the registry
    for field_name, provider_map in FIELD_REGISTRY.items():
        mapping = provider_map.get(provider)
        if mapping is None:
            continue
        # Skip people-only enum fields for company searches
        if entity_type == "companies" and field_name in ("seniority", "department"):
            continue
        filters[field_name] = {"type": "enum", "values": list(mapping.values)}

    # Text fields
    for text_field in _TEXT_FILTERS.get(entity_type, []):
        filters[text_field] = {"type": "text"}

    return DataEnvelope(data={
        "provider": provider,
        "entity_type": entity_type,
        "filters": filters,
    })


@router.post("/search")
async def intent_search(
    body: IntentSearchRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    if not body.criteria:
        return DataEnvelope(data={
            "search_type": body.search_type,
            "provider_used": "none",
            "results": [],
            "result_count": 0,
            "enum_resolution": {},
            "unresolved_fields": [],
            "pagination": None,
            "provider_attempts": [],
            "status": "failed",
            "missing_inputs": ["criteria"],
        })

    result = await execute_intent_search(
        search_type=body.search_type,
        criteria=body.criteria,
        provider=body.provider,
        limit=body.limit,
        page=body.page,
        cursor=body.cursor,
    )

    output = IntentSearchOutput.model_validate(result)
    return DataEnvelope(data=output.model_dump())
