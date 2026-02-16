# app/main.py — FastAPI app entry point

from fastapi import FastAPI

from app.routers import admin, companies, health, pipelines, steps, submissions

app = FastAPI(
    title="data-engine-x-api",
    description="Multi-tenant data processing engine",
    version="0.1.0",
)

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(companies.router, prefix="/companies", tags=["companies"])
app.include_router(submissions.router, prefix="/submissions", tags=["submissions"])
app.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
app.include_router(steps.router, prefix="/steps", tags=["steps"])
