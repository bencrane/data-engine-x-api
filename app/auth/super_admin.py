# app/auth/super_admin.py — Super admin JWT validation and dependency

from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.models import SuperAdminContext
from app.config import get_settings
from app.database import get_supabase_client

security = HTTPBearer()


class SuperAdminTokenPayload(BaseModel):
    sub: str
    email: str
    type: str
    exp: int | None = None
    iat: int | None = None


def decode_super_admin_jwt(token: str) -> SuperAdminTokenPayload:
    """Decode and validate a super-admin JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.super_admin_jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    parsed = SuperAdminTokenPayload(**payload)
    if parsed.type != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type for super admin endpoints",
        )
    return parsed


async def get_current_super_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> SuperAdminContext:
    """
    Validate super-admin JWT and ensure active super_admin record exists.
    """
    token = credentials.credentials
    payload = decode_super_admin_jwt(token)

    client = get_supabase_client()
    result = (
        client.table("super_admins")
        .select("id, email, is_active")
        .eq("id", payload.sub)
        .eq("email", payload.email)
        .single()
        .execute()
    )

    if not result.data or not result.data.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Super admin not found or inactive",
        )

    return SuperAdminContext(
        super_admin_id=UUID(result.data["id"]),
        email=result.data["email"],
    )
