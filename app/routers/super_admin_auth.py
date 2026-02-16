# app/routers/super_admin_auth.py — Super-admin authentication endpoints

import bcrypt
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import SuperAdminContext, get_current_super_admin
from app.auth.super_admin import create_super_admin_jwt
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


class SuperAdminLoginRequest(BaseModel):
    email: str
    password: str


class SuperAdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SuperAdminMeResponse(BaseModel):
    super_admin_id: str
    email: str


@router.post("/login", response_model=DataEnvelope, responses={401: {"model": ErrorEnvelope}})
async def super_admin_login(
    payload: SuperAdminLoginRequest,
) -> DataEnvelope:
    """Super-admin login via email/password."""
    normalized_email = payload.email.strip().lower()
    client = get_supabase_client()
    result = (
        client.table("super_admins")
        .select("id, email, password_hash, is_active")
        .eq("email", normalized_email)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Invalid credentials", 401)

    admin = result.data[0]
    if not admin.get("is_active"):
        return error_response("Super admin is inactive", 401)

    password_hash = admin.get("password_hash")
    if not password_hash or not bcrypt.checkpw(
        payload.password.encode("utf-8"),
        password_hash.encode("utf-8"),
    ):
        return error_response("Invalid credentials", 401)

    token = create_super_admin_jwt(
        super_admin_id=admin["id"],
        email=admin["email"],
    )
    return DataEnvelope(data=SuperAdminLoginResponse(access_token=token).model_dump())


@router.post("/me", response_model=DataEnvelope)
async def super_admin_me(
    super_admin: SuperAdminContext = Depends(get_current_super_admin),
) -> DataEnvelope:
    """Protected super-admin endpoint used for auth verification."""
    return DataEnvelope(
        data=SuperAdminMeResponse(
            super_admin_id=str(super_admin.super_admin_id),
            email=super_admin.email,
        ).model_dump()
    )
