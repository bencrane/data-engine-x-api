# app/auth/models.py — AuthContext, TokenPayload

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class SessionTokenPayload(BaseModel):
    sub: str
    user_id: str
    org_id: str
    company_id: str | None = None
    role: str
    type: str = "session"
    exp: int | None = None
    iat: int | None = None


class AuthContext(BaseModel):
    user_id: str | None = None
    org_id: str
    company_id: str | None = None
    role: str
    auth_method: Literal["jwt", "api_token"]

    @property
    def is_service_account(self) -> bool:
        return self.auth_method == "api_token"

    @property
    def is_admin(self) -> bool:
        return self.role in {"org_admin", "company_admin"}


@dataclass
class SuperAdminContext:
    super_admin_id: UUID
    email: str
