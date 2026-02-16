# CLAUDE.md

This file provides guidance to Claude Code when working with this codebase.

## Project Overview

data-engine-x-api is a multi-tenant data processing engine built with:
- **FastAPI** (hosted on Railway) — API layer
- **Modal** — Serverless compute for data processing steps
- **Supabase** (Postgres) — Database
- **Prefect** — Pipeline orchestration

## Key Conventions

- **All endpoints use POST** — consistent with engine-x family
- **AuthContext injected via dependency** on every endpoint
- **Every query scoped by org_id** at minimum
- **Modal functions are stateless** — receive input, return output, no side effects
- **Prefect flows handle orchestration** — retry, failure, sequencing
- **Step registry is database-driven** — no hardcoded step lists in code

## Multi-Tenancy Hierarchy

```
Org → Company → Submission → Pipeline Run → Step Results
```

## Common Commands

```bash
# Run API locally
uvicorn app.main:app --reload

# Deploy Modal app
modal deploy modal_app

# Run Prefect flows locally
prefect server start
```

## Directory Structure

- `app/` — FastAPI application
- `modal_app/` — Modal functions and Prefect flows
- `supabase/migrations/` — Database migrations
- `docs/` — Documentation
