# AGENT_HANDOFF

Date: 2026-02-17
Repository: `data-engine-x-api`
Primary branch: `main`
Current HEAD at handoff update: `26bcbf6` (local `main`)

## 1) Project Snapshot

`data-engine-x-api` is a multi-tenant entity intelligence backend with operation-native execution, batch orchestration, fan-out child pipelines, canonical entity state, and timeline history.

Core stack:
- FastAPI
- Trigger.dev
- Supabase/Postgres

Read first:
- `CLAUDE.md`
- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/ARCHITECTURE.md`

## 2) Current Git/State Notes

Local `main` may be ahead of `origin/main`. Verify with `git status` and `git log` before release actions.

Local temp artifacts can exist (for example `.tmp-docker-config/`) and should remain uncommitted unless explicitly requested.

## 3) Live Operation IDs (execute v1)

All are wired through `POST /api/v1/execute` and persisted to `operation_runs` / `operation_attempts`:

1. `person.contact.resolve_email`
2. `person.contact.resolve_mobile_phone`
3. `person.contact.verify_email`
4. `person.search`
5. `company.search`
6. `company.enrich.profile`
7. `company.research.resolve_g2_url`
8. `company.research.resolve_pricing_page_url`
9. `company.ads.search.linkedin`
10. `company.ads.search.meta`
11. `company.ads.search.google`

## 4) Provider Order / Config Defaults

Defined in `app/config.py` and `.env.example` (non-prefixed env names):

- `COMPANY_SEARCH_ORDER=prospeo,blitzapi,companyenrich`
- `PERSON_SEARCH_ORDER=prospeo,blitzapi,companyenrich`
- `PERSON_RESOLVE_MOBILE_ORDER=leadmagic,blitzapi`
- `COMPANY_ENRICH_PROFILE_ORDER=prospeo,blitzapi,companyenrich,leadmagic`

`person.contact.resolve_email` runtime waterfall is LeadMagic-first (`leadmagic -> icypeas -> parallel` fallback), with verification after resolution (`millionverifier -> reoon`).

LLM routing:
- `LLM_PRIMARY_MODEL=gemini`
- `LLM_FALLBACK_MODEL=gpt-4`

Adyntel:
- `ADYNTEL_API_KEY`
- `ADYNTEL_ACCOUNT_EMAIL`
- `ADYNTEL_TIMEOUT_SECONDS=90`

## 5) What Is Implemented

- Batch orchestration (`/api/v1/batch/submit`, `/api/v1/batch/status`)
- Fan-out parent/child pipeline runs from operation outputs
- Entity state upsert/versioning (`company_entities`, `person_entities`)
- Entity timeline recording (`entity_timeline`) for upsert and fan-out events
- Provider adapter audit trail in `operation_attempts`
- Canonical operation contracts in `app/contracts/`
- 11 active operation IDs in execute v1
- Trigger.dev <-> FastAPI internal callback path (`/api/internal/*`)
- Doppler-based secrets management (`doppler run` in `Dockerfile`, `DOPPLER_TOKEN` on Railway)

## 6) Recommended Next Steps

1. Add `person.enrich.profile` operation.
2. Add `max_results` and `provider_overrides` support to `person.search`.
3. Increase entity enrichment log depth (per-step timeline events, not only upsert/fan-out summaries).
4. Improve frontend batch-status display for parent/child run lineage and per-entity context.

## 7) Non-Negotiable Guardrails

1. Keep changes scope-bound to explicit user requests.
2. Do not run deploy commands unless explicitly requested.
3. Do not alter provider adapters without explicit scope.
4. Keep operation contracts canonical and provider-agnostic.

## 8) Quick File Map

Main API/flow entrypoints:
- `app/main.py`
- `app/routers/execute_v1.py`
- `app/routers/entities_v1.py`
- `app/routers/internal.py`
- `app/services/submission_flow.py` (batch + fan-out)
- `app/services/entity_state.py`
- `app/services/entity_timeline.py`

Operation services:
- `app/services/email_operations.py`
- `app/services/search_operations.py`
- `app/services/company_operations.py`
- `app/services/research_operations.py`
- `app/services/adyntel_operations.py`
- `app/services/operation_history.py`

Contracts/providers:
- `app/contracts/`
- `app/providers/`

Runtime/orchestration:
- `trigger/src/tasks/run-pipeline.ts`
- `trigger/src/tasks/execute-step.ts` (legacy path)

Infra/tooling:
- `Dockerfile`
- `scripts/`

Tests:
- `tests/`

Schema:
- `supabase/migrations/001_initial_schema.sql`
- `supabase/migrations/002_users_password_hash.sql`
- `supabase/migrations/003_api_tokens_user_id.sql`
- `supabase/migrations/004_steps_executor_config.sql`
- `supabase/migrations/005_operation_execution_history.sql`
- `supabase/migrations/006_blueprint_operation_steps.sql`
- `supabase/migrations/007_entity_state.sql`
- `supabase/migrations/008_companies_domain.sql`
- `supabase/migrations/009_entity_timeline.sql`
- `supabase/migrations/010_fan_out.sql`

## 9) Operator Intent Summary

- Keep architecture pragmatic and contract-first.
- Preserve deterministic run lineage and provider auditability.
- Prioritize production-safe behavior under mixed/noisy context inputs.
