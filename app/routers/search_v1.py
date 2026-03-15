from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.contracts.intent_search import IntentSearchOutput, IntentSearchRequest
from app.routers._responses import DataEnvelope, error_response
from app.services.intent_search import execute_intent_search

router = APIRouter()
_security = HTTPBearer(auto_error=False)


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


@router.post("/search")
async def intent_search(
    request: Request,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    body = await request.json()
    try:
        parsed = IntentSearchRequest.model_validate(body)
    except Exception as exc:
        return error_response(f"Invalid request: {exc}", status_code=422)

    limit = max(1, min(parsed.limit, 100))
    page = max(1, parsed.page)

    if not parsed.criteria:
        return DataEnvelope(data={
            "search_type": parsed.search_type,
            "provider_used": "none",
            "results": [],
            "result_count": 0,
            "enum_resolution": {},
            "unresolved_fields": [],
            "pagination": None,
            "status": "failed",
            "missing_inputs": ["criteria"],
        })

    result = await execute_intent_search(
        search_type=parsed.search_type,
        criteria=parsed.criteria,
        provider=parsed.provider,
        limit=limit,
        page=page,
    )

    output = IntentSearchOutput.model_validate(result)
    return DataEnvelope(data=output.model_dump())
