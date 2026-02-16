# app/auth/tokens.py — API token + JWT validation

import jwt
from fastapi import HTTPException, status

from app.config import get_settings
from app.auth.models import TokenPayload


def decode_jwt(token: str) -> TokenPayload:
    """Decode and validate a tenant JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        parsed = TokenPayload(**payload)
        token_type = parsed.type or "user"
        if token_type != "user":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type for tenant endpoints",
            )
        return parsed
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


def validate_internal_api_key(api_key: str) -> bool:
    """Validate internal API key for service-to-service calls."""
    settings = get_settings()
    return api_key == settings.internal_api_key
