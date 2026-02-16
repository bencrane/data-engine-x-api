# data-engine-x-api

Multi-tenant data processing engine. FastAPI app hosted on Railway, proxying to Modal for compute. Supabase (Postgres) for data. Prefect for pipeline orchestration.

## What This System Does

Receives raw CRM/company data submissions, runs them through registered enrichment/cleaning steps (each a Modal function), orchestrated by Prefect in a waterfall sequence defined by a "recipe." Results are delivered back to a dashboard, CRM, or both.

## Multi-Tenancy Model

```
Org (e.g., Revenue Activation)
  └── Company (client whose data is being processed)
        └── Submission (a batch of data + recipe to run)
              └── Pipeline Run (orchestrated execution of steps)
                    └── Step Results (output of each enrichment function)
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env

# Run locally
uvicorn app.main:app --reload
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture decisions.
