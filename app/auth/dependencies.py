# app/auth/dependencies.py — get_current_auth → AuthContext

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import AuthContext
from app.auth.tokens import decode_jwt, validate_internal_api_key

security = HTTPBearer()


async def get_current_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthContext:
    """
    Extract and validate authentication from request.
    Returns AuthContext with org_id for query scoping.
    """
    token = credentials.credentials

    # Check if it's an internal API key
    if validate_internal_api_key(token):
        # Internal service calls need to pass org_id in a header
        # This is a simplified version; expand as needed
        return AuthContext(
            org_id="internal",
            is_service_account=True,
            is_admin=True,
        )

    # Otherwise, treat as JWT
    payload = decode_jwt(token)

    return AuthContext(
        user_id=payload.sub,
        org_id=payload.org_id,
        is_service_account=False,
        is_admin=False,
    )
