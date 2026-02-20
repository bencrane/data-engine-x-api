# data-engine-x-api

Multi-tenant data processing engine. FastAPI app hosted on Railway for API/auth/persistence, Trigger.dev for orchestration + task execution, and Supabase (Postgres) for data.

## What This System Does

Receives raw CRM/company data submissions, runs them through registered enrichment/cleaning steps (each a Trigger.dev task), orchestrated in a waterfall sequence defined by a "blueprint." Results are delivered back to a dashboard, CRM, or both.

## Multi-Tenancy Model

```
Org (e.g., Revenue Activation)
  └── Company (client whose data is being processed)
        └── Submission (a batch of data + blueprint to run)
              └── Pipeline Run (orchestrated execution of steps)
                    └── Step Results (output of each enrichment task)
```

## Quick Start

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Trigger.dev dependencies
cd trigger && npm install && cd ..

# Copy environment template
cp .env.example .env

# Run API locally
uvicorn app.main:app --reload

# Run Trigger.dev dev server (in another terminal)
cd trigger && npm run dev
```

## Architecture

- **FastAPI (Railway)**: API layer, auth, data persistence, triggers pipeline runs
- **Trigger.dev**: Task orchestration and execution
- **Supabase**: Database for orgs, companies, submissions, step registry, results

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture decisions.

