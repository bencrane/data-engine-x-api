# app/routers/providers_v1.py — Provider account/status endpoints

from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.config import get_settings
from app.providers.prospeo import get_account_information
from app.routers._responses import DataEnvelope, error_response

router = APIRouter()
_security = HTTPBearer(auto_error=False)


async def _resolve_flexible_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthContext | SuperAdminContext:
    from fastapi import HTTPException, status

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    try:
        return await get_current_super_admin(credentials)
    except HTTPException:
        pass
    return await get_current_auth(request=request, credentials=credentials)


@router.post(
    "/providers/prospeo/account",
    response_model=DataEnvelope,
)
async def prospeo_account_info(
    _auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    settings = get_settings()
    result = await get_account_information(api_key=settings.prospeo_api_key)

    if result.get("error"):
        if result.get("error_message") == "missing_provider_api_key":
            return error_response("Prospeo API key not configured", 503)
        return error_response(
            f"Prospeo API error: {result.get('error_code', 'unknown')}",
            502,
        )

    return DataEnvelope(data=result)
