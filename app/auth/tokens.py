# app/auth/tokens.py — JWT/API-token helpers

from datetime import datetime, timedelta, timezone
import hashlib

import jwt

from app.auth.models import SessionTokenPayload
from app.config import get_settings


class JWTDecodeError(Exception):
    """Raised when a JWT cannot be decoded/validated."""


class InvalidJWTTypeError(Exception):
    """Raised when a JWT has a valid signature but unsupported type."""


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_tenant_session_jwt(
    *,
    user_id: str,
    org_id: str,
    company_id: str | None,
    role: str,
    expires_in_hours: int = 24,
) -> str:
    """Create a tenant session JWT."""
    settings = get_settings()
    now = _now_utc()
    payload = {
        "type": "session",
        "sub": user_id,
        "user_id": user_id,
        "org_id": org_id,
        "company_id": company_id,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_in_hours)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_tenant_session_jwt(token: str) -> SessionTokenPayload:
    """
    Decode tenant JWT.
    Raises InvalidJWTTypeError if token is valid JWT but wrong type.
    Raises JWTDecodeError for invalid/expired signatures and payloads.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise JWTDecodeError(str(exc)) from exc

    token_type = payload.get("type", "session")
    if token_type != "session":
        raise InvalidJWTTypeError(f"Unsupported JWT type: {token_type}")

    try:
        return SessionTokenPayload(
            sub=payload.get("sub") or payload.get("user_id"),
            user_id=payload.get("user_id") or payload.get("sub"),
            org_id=payload["org_id"],
            company_id=payload.get("company_id"),
            role=payload["role"],
            type="session",
            exp=payload.get("exp"),
            iat=payload.get("iat"),
        )
    except KeyError as exc:
        raise JWTDecodeError(f"Missing JWT claim: {exc}") from exc


def hash_api_token(raw_token: str) -> str:
    """Return deterministic SHA-256 hash for API token lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
