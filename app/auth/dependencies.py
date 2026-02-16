# app/auth/dependencies.py — get_current_auth → AuthContext

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import AuthContext
from app.auth.tokens import (
    InvalidJWTTypeError,
    JWTDecodeError,
    decode_tenant_session_jwt,
    hash_api_token,
)
from app.database import get_supabase_client

security = HTTPBearer(auto_error=False)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = value.replace("Z", "+00:00")
    return datetime.fromisoformat(parsed)


async def get_current_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AuthContext:
    """
    Resolve tenant auth from bearer token:
    1) session JWT
    2) API token hash lookup
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

    token = credentials.credentials

    # First: try tenant session JWT.
    try:
        payload = decode_tenant_session_jwt(token)
        return AuthContext(
            user_id=payload.user_id,
            org_id=payload.org_id,
            company_id=payload.company_id,
            role=payload.role,
            auth_method="jwt",
        )
    except InvalidJWTTypeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid JWT type for tenant endpoints",
        )
    except JWTDecodeError:
        pass

    # Fallback: API token lookup by SHA-256 hash.
    client = get_supabase_client()
    token_hash = hash_api_token(token)
    token_result = (
        client.table("api_tokens")
        .select("id, org_id, company_id, role, expires_at, revoked_at")
        .eq("token_hash", token_hash)
        .limit(1)
        .execute()
    )
    if not token_result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    token_record = token_result.data[0]

    if token_record.get("revoked_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token is revoked",
        )

    expires_at = _parse_timestamp(token_record.get("expires_at"))
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API token is expired",
        )

    # Best-effort usage tracking.
    client.table("api_tokens").update(
        {"last_used_at": datetime.now(timezone.utc).isoformat()}
    ).eq("id", token_record["id"]).execute()

    return AuthContext(
        user_id=None,
        org_id=token_record["org_id"],
        company_id=token_record.get("company_id"),
        role=token_record["role"],
        auth_method="api_token",
    )
