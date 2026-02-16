# app/auth/models.py — AuthContext, TokenPayload

from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel


class TokenPayload(BaseModel):
    sub: str  # Subject (user ID or API key ID)
    org_id: str
    type: str | None = None
    exp: int | None = None
    iat: int | None = None


class AuthContext(BaseModel):
    user_id: str | None = None
    org_id: str
    is_service_account: bool = False
    is_admin: bool = False


@dataclass
class SuperAdminContext:
    super_admin_id: UUID
    email: str
