# AGENT_HANDOFF

Date: 2026-02-16
Repository: `data-engine-x-api`
Primary branch: `main`
Current HEAD at handoff update: `f9eca25` (local `main`)

## 1) Project Snapshot

`data-engine-x-api` is a multi-tenant entity intelligence API with operation execution, batch orchestration, and persistent entity state.

Core stack:
- FastAPI API layer
- Trigger.dev tasks
- Supabase/Postgres persistence

Core architectural direction:
- Contract-first operations
- Provider adapters behind canonical operation IDs
- Durable execution logs (`operation_runs`, `operation_attempts`)
- Single-entity execution via `POST /api/v1/execute`
- Batch execution via `POST /api/v1/batch/submit` + `POST /api/v1/batch/status`
- Entity state upsert/query via internal callbacks and `/api/v1/entities/*`

Read first:
- `CLAUDE.md`
- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/ENTITY_INTELLIGENCE_ARCHITECTURE.md`
- `docs/EXPORT_CONTRACT_V1.md`

## 2) Current Git/State Notes

Repository has multiple local commits ahead of `origin/main`; use `git status` and `git log` before release operations.

At handoff time, local uncommitted items may exist (check `git status`), commonly:
- `docs/POSTMORTEM_2026-02-16_DEPLOY_FLOW_MISFIRE.md`
- `.tmp-docker-config/`

Treat `.tmp-docker-config/` as local temp unless user explicitly asks to keep/commit.

## 3) Live Operation IDs (execute v1)

All below are wired through `POST /api/v1/execute` and persisted via `persist_operation_execution(...)`.

Person/contact:
- `person.contact.resolve_email`
- `person.contact.verify_email`
- `person.contact.resolve_mobile_phone`

Search:
- `company.search`
- `person.search`

Company enrichment/research:
- `company.enrich.profile`
- `company.research.resolve_g2_url`
- `company.research.resolve_pricing_page_url`

Ads (Adyntel only):
- `company.ads.search.linkedin`
- `company.ads.search.meta`
- `company.ads.search.google`

## 4) Provider Order / Config Defaults

Defined in `app/config.py` + `.env.example`:

- `DATA_ENGINE_COMPANY_SEARCH_ORDER=prospeo,blitzapi,companyenrich`
- `DATA_ENGINE_PERSON_SEARCH_ORDER=prospeo,blitzapi,companyenrich`
- `DATA_ENGINE_PERSON_RESOLVE_MOBILE_ORDER=leadmagic,blitzapi`
- `DATA_ENGINE_COMPANY_ENRICH_PROFILE_ORDER=prospeo,blitzapi,companyenrich,leadmagic`

LLM routing:
- `DATA_ENGINE_LLM_PRIMARY_MODEL=gemini`
- `DATA_ENGINE_LLM_FALLBACK_MODEL=gpt-4`

Adyntel:
- `DATA_ENGINE_ADYNTEL_API_KEY`
- `DATA_ENGINE_ADYNTEL_EMAIL`
- `DATA_ENGINE_ADYNTEL_TIMEOUT_SECONDS=90`

## 5) What Is Implemented

Implemented:
- Operation endpoints and provider-adapter-backed execution (`POST /api/v1/execute`)
- Durable operation history (`operation_runs`, `operation_attempts`)
- Config-driven provider ordering in `app/config.py`
- Batch orchestration:
  - `POST /api/v1/batch/submit` creates one submission and one pipeline run per entity
  - `POST /api/v1/batch/status` aggregates per-entity run status and final context
- Trigger orchestrator bridge:
  - FastAPI triggers `run-pipeline`
  - Trigger uses internal HTTP callbacks under `/api/internal/*`
  - Internal service auth via `DATA_ENGINE_INTERNAL_API_KEY`
- Cumulative output chaining across operation steps in Trigger runtime
- Entity state persistence (`company_entities`, `person_entities`) with versioned upserts
- Entity query endpoints:
  - `POST /api/v1/entities/companies`
  - `POST /api/v1/entities/persons`
- Test suite coverage for contracts, batch flow, and entity state in `tests/`

## 6) Immediate Recommended Next Steps

1. Deployment readiness validation:
   - run the manual smoke script against deployed FastAPI + Trigger + DB
   - verify entity upsert and query round-trip in live environment

2. Operational hardening:
   - add dashboard/alerts for pipeline run failure rates and internal callback failures
   - establish runbook for provider outages and timeout tuning

3. Contract quality guardrails:
   - expand canonical output assertions for all operation IDs and fallback paths
   - enforce schema-level constraints where drift risk remains

4. Release process:
   - execute migration manifest in order on target DB
   - validate environment variable completeness before production deploy

## 7) Non-Negotiable Execution Guardrails

This is critical for continuity with the operator.

1. Do only what the user explicitly asks.
2. Do not add extra commands/actions "proactively."
3. Do not run platform deploy commands unless explicitly requested.
4. For this repo’s deploy flow, default is `git commit` + `git push`; Railway deploy is GitHub-driven.
5. If ambiguous, ask one short clarification, then wait.
6. Keep responses concise and scope-bound.

## 8) Quick File Map for New Agent

Main entrypoints:
- `app/routers/execute_v1.py`
- `app/routers/entities_v1.py`
- `app/routers/internal.py`
- `app/services/email_operations.py`
- `app/services/search_operations.py`
- `app/services/company_operations.py`
- `app/services/research_operations.py`
- `app/services/adyntel_operations.py`
- `app/services/submission_flow.py`
- `app/services/entity_state.py`
- `app/services/operation_history.py`
- `app/services/trigger.py`
- `app/config.py`

Contracts/providers:
- `app/contracts/`
- `app/providers/`

Trigger runtime:
- `trigger/src/tasks/run-pipeline.ts`
- `trigger/src/tasks/execute-step.ts` (legacy generic executor path)

Tests:
- `tests/test_contracts.py`
- `tests/test_batch_flow.py`
- `tests/test_entity_state.py`

Schema/migrations (current):
- `supabase/migrations/001_initial_schema.sql`
- `supabase/migrations/002_users_password_hash.sql`
- `supabase/migrations/003_api_tokens_user_id.sql`
- `supabase/migrations/004_steps_executor_config.sql`
- `supabase/migrations/005_operation_execution_history.sql`
- `supabase/migrations/006_blueprint_operation_steps.sql`
- `supabase/migrations/007_entity_state.sql`

## 9) Operator Intent Summary

Top product intent:
- Single-company to outbound-intelligence flow
- High pragmatism, low ceremony
- Minimal overengineering
- Provider costs and control matter
- User authority is the hard boundary for execution behavior
