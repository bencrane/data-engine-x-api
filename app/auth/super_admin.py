# app/auth/super_admin.py — Super admin JWT validation and dependency

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth.models import SuperAdminContext
from app.config import get_settings
from app.database import get_supabase_client

security = HTTPBearer(auto_error=False)


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


def create_super_admin_jwt(
    *,
    super_admin_id: str,
    email: str,
    expires_in_hours: int = 24,
) -> str:
    """Create a super-admin JWT token."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "type": "super_admin",
        "sub": super_admin_id,
        "super_admin_id": super_admin_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_in_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.super_admin_jwt_secret, algorithm="HS256")


async def get_current_super_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> SuperAdminContext:
    """
    Validate super-admin JWT and ensure active super_admin record exists.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )

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
