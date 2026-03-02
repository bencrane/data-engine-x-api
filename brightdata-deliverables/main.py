from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import leads, filters, views, auth, companies, enrichment, people, admin, run, read, hq, workflows, pipeline, parallel_native, job_boards, brightdata_ingest
from db import init_pool, close_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database pool
    await init_pool()
    yield
    # Shutdown: close database pool
    await close_pool()


app = FastAPI(
    title="HQ Master Data API",
    description="API for querying the HQ canonical leads database",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    redirect_slashes=False,  # Prevent 307 redirects that break POST requests from Clay
)

# CORS - allowed origins for revenueactivation.com and radarrevenue.com
ALLOWED_ORIGINS = [
    # revenueactivation.com
    "https://revenueactivation.com",
    "https://app.revenueactivation.com",
    "https://admin.revenueactivation.com",
    "https://hq.revenueactivation.com",
    "https://demo.revenueactivation.com",
    # radarrevenue.com
    "https://radarrevenue.com",
    "https://app.radarrevenue.com",
    "https://admin.radarrevenue.com",
    "https://hq.radarrevenue.com",
    "https://demo.radarrevenue.com",
    # localhost for development (ports 3000-3015)
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://localhost:3004",
    "http://localhost:3005",
    "http://localhost:3006",
    "http://localhost:3007",
    "http://localhost:3008",
    "http://localhost:3009",
    "http://localhost:3010",
    "http://localhost:3011",
    "http://localhost:3012",
    "http://localhost:3013",
    "http://localhost:3014",
    "http://localhost:3015",
    "http://localhost:5173",
    # admin tools
    "https://find-similar-companies-admin.vercel.app",
    "https://opsinternal.com",
    "https://www.opsinternal.com",
    "https://app.opsinternal.com",
    "https://admin.opsinternal.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(leads.router)
app.include_router(filters.router)
app.include_router(views.router)
app.include_router(auth.router)
app.include_router(companies.router)
app.include_router(enrichment.router)
app.include_router(people.router)
app.include_router(admin.router)
app.include_router(run.router)
app.include_router(read.router)
app.include_router(hq.router)
app.include_router(workflows.router)
app.include_router(pipeline.router)
app.include_router(parallel_native.router)
app.include_router(job_boards.router)
app.include_router(brightdata_ingest.router)


@app.get("/")
async def root():
    return {
        "name": "HQ Master Data API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
