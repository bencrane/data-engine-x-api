# data-engine-x-api

Multi-tenant data processing engine. FastAPI runs the API/auth/persistence layer on Railway, Trigger.dev handles orchestration and task execution, and Supabase/Postgres stores execution lineage plus entity intelligence.

## Chief Agent Start Here

If you are onboarding as a Chief Agent, do not start with older architecture docs.

Use this reading order:

1. `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`
2. `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
3. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
4. `CLAUDE.md`
5. `docs/CHIEF_AGENT_DIRECTIVE.md`
6. `docs/WRITING_EXECUTOR_DIRECTIVES.md`

Authority boundary:

- Production truth: `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`, `docs/DATA_ENGINE_X_ARCHITECTURE.md`, `CLAUDE.md`
- Doctrine: `docs/STRATEGIC_DIRECTIVE.md`, `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- Broad reference: `docs/SYSTEM_OVERVIEW.md`
- Historical/lower-authority context: `docs/ARCHITECTURE.md`, `docs/AGENT_HANDOFF.md`, `docs/COMPREHENSION.md`

`docs/EXECUTOR_DIRECTIVE_*.md` files are work-scope and style artifacts. They are not proof that the described work shipped or is healthy in production.

## What This System Does

The system receives CRM, company, person, job, and FMCSA-related inputs, runs them through deterministic operation-backed pipelines, and persists execution history plus canonical entity intelligence for downstream querying and workflow use.

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

# Configure Doppler for this repo first
# See docs/DOPPLER_RAILWAY_SETUP.md

# Run API locally
doppler run -- uvicorn app.main:app --reload

# Run Trigger.dev dev server (in another terminal)
cd trigger && doppler run -- npm run dev
```

## Documentation Guide

- `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md` - first-click authority map for new Chief Agents
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` - audited production-state baseline
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` - ground-truth architecture and known production problems
- `CLAUDE.md` - project rules, truth precedence, deploy protocol, and current workstream framing
- `docs/CHIEF_AGENT_DIRECTIVE.md` - Chief Agent role and onboarding rules
- `docs/WRITING_EXECUTOR_DIRECTIVES.md` - canonical directive-writing template and constraints
- `docs/STRATEGIC_DIRECTIVE.md` - doctrine and intended design rules, not live-status proof
- `docs/SYSTEM_OVERVIEW.md` - broad technical reference
- `docs/ARCHITECTURE.md` - older architecture snapshot retained for historical context only

## Runtime Shape

- **FastAPI (Railway)**: API layer, auth, data persistence, internal callbacks
- **Trigger.dev**: pipeline orchestration, fan-out, cumulative context chaining
- **Supabase/Postgres**: org/company/user data, submissions, runs, step results, entity state, timeline

