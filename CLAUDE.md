# CLAUDE.md

This file provides guidance to Claude Code when working with this codebase.

## Project Overview

data-engine-x-api is a multi-tenant data processing engine built with:
- **FastAPI** (hosted on Railway) — API layer
- **Trigger.dev** — Task orchestration and execution
- **Supabase** (Postgres) — Database

## Key Conventions

- **All endpoints use POST** — consistent with engine-x family
- **AuthContext injected via dependency** on every endpoint
- **Every query scoped by org_id** at minimum
- **Trigger.dev tasks are stateless** — receive input, return output
- **Step registry is database-driven** — no hardcoded step lists in code

## Multi-Tenancy Hierarchy

```
Org → Company → Submission → Pipeline Run → Step Results
```

## Common Commands

```bash
# Run API locally
uvicorn app.main:app --reload

# Run Trigger.dev dev server
cd trigger && npm run dev

# Deploy Trigger.dev tasks
cd trigger && npm run deploy
```

## Directory Structure

- `app/` — FastAPI application
- `trigger/` — Trigger.dev tasks and workflows
- `supabase/migrations/` — Database migrations
- `docs/` — Documentation
