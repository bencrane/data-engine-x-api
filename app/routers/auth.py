# app/routers/auth.py — Tenant authentication endpoints

import bcrypt
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.auth.tokens import create_tenant_session_jwt
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TenantMeResponse(BaseModel):
    user_id: str | None = None
    org_id: str
    company_id: str | None = None
    role: str
    auth_method: str


@router.post("/login", response_model=DataEnvelope, responses={401: {"model": ErrorEnvelope}})
async def login(payload: LoginRequest) -> DataEnvelope:
    """Tenant session login via email/password."""
    normalized_email = payload.email.strip().lower()
    client = get_supabase_client()
    result = (
        client.table("users")
        .select("id, org_id, company_id, role, is_active, password_hash")
        .eq("email", normalized_email)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Invalid credentials", 401)

    user = result.data[0]
    password_hash = user.get("password_hash")
    if not user.get("is_active") or not password_hash:
        return error_response("Invalid credentials", 401)

    if not bcrypt.checkpw(
        payload.password.encode("utf-8"),
        password_hash.encode("utf-8"),
    ):
        return error_response("Invalid credentials", 401)

    token = create_tenant_session_jwt(
        user_id=user["id"],
        org_id=user["org_id"],
        company_id=user.get("company_id"),
        role=user["role"],
    )
    return DataEnvelope(data=LoginResponse(access_token=token).model_dump())


@router.post("/me", response_model=DataEnvelope)
async def me(auth: AuthContext = Depends(get_current_auth)) -> DataEnvelope:
    """Protected tenant endpoint used for auth verification."""
    return DataEnvelope(data=TenantMeResponse(**auth.model_dump()).model_dump())
