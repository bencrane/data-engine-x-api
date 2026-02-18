# app/main.py — FastAPI app entry point

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.routers import (
    auth,
    entities_v1,
    execute_v1,
    health,
    internal,
    registry_v1,
    super_admin_api,
    super_admin_auth,
    super_admin_flow,
    tenant_blueprints,
    tenant_companies,
    tenant_flow,
    tenant_steps,
    tenant_users,
)

app = FastAPI(
    title="data-engine-x-api",
    description="Multi-tenant data processing engine",
    version="0.1.0",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(
    internal.router,
    prefix="/api/internal",
    tags=["internal"],
)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(
    super_admin_auth.router,
    prefix="/api/super-admin",
    tags=["super-admin-auth"],
)
app.include_router(
    super_admin_api.router,
    prefix="/api/super-admin",
    tags=["super-admin"],
)
app.include_router(
    super_admin_flow.router,
    prefix="/api/super-admin",
    tags=["super-admin-flow"],
)
app.include_router(
    tenant_companies.router,
    prefix="/api/companies",
    tags=["tenant-companies"],
)
app.include_router(
    tenant_blueprints.router,
    prefix="/api/blueprints",
    tags=["tenant-blueprints"],
)
app.include_router(
    tenant_steps.router,
    prefix="/api/steps",
    tags=["tenant-steps"],
)
app.include_router(
    tenant_users.router,
    prefix="/api/users",
    tags=["tenant-users"],
)
app.include_router(
    tenant_flow.router,
    prefix="/api",
    tags=["tenant-flow"],
)
app.include_router(
    execute_v1.router,
    prefix="/api/v1",
    tags=["execute-v1"],
)
app.include_router(
    entities_v1.router,
    prefix="/api/v1/entities",
    tags=["entities-v1"],
)
app.include_router(
    registry_v1.router,
    prefix="/api/v1/registry",
    tags=["registry-v1"],
)
