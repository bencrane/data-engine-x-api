# Directive: Priority 2 — First Dedicated Workflow File (Company Enrichment)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The current pipeline runner (`trigger/src/tasks/run-pipeline.ts`) is a ~2,700-line monolith that interprets blueprint JSON at runtime. It owns too many responsibilities and its auto-persist pattern silently swallows write failures — the primary source of production data loss. We are replacing it with dedicated workflow files: one explicit Trigger.dev task per pipeline, with shared utility modules for the common patterns.

This is the first dedicated workflow. It sets the pattern that all subsequent workflows will follow. The shared utility modules you create here become the foundation for every future workflow file.

---

## The Problem

A company domain goes in. Enriched company entity state comes out. Today this is handled by `run-pipeline.ts` interpreting a blueprint at runtime. The new workflow should be a standalone Trigger.dev task with explicit steps, clear error semantics, and confirmed persistence — not fire-and-forget.

**What "confirmed persistence" means:** When the workflow writes entity state or dedicated table data via a FastAPI internal endpoint, it must verify the write succeeded. If the write fails, the workflow must know about it and handle it explicitly (whether that means failing the workflow, retrying, or recording the failure is your engineering decision). The current pattern of wrapping writes in try/catch and logging a warning while the pipeline continues is what we are replacing.

---

## Architectural Constraints

1. **This is a new Trigger.dev task.** It lives in `trigger/src/tasks/` as a new file. It does NOT modify `run-pipeline.ts`.

2. **FastAPI still owns all database writes.** The workflow calls FastAPI internal endpoints to execute operations, upsert entity state, and write to dedicated tables. The runtime boundary (Trigger.dev calls FastAPI via internal HTTP) does not change.

3. **Internal auth model:** Trigger.dev → FastAPI calls use `Authorization: Bearer <INTERNAL_API_KEY>` with `x-internal-org-id` and `x-internal-company-id` headers. See `CLAUDE.md` auth section.

4. **Shared utilities must be reusable.** The utility modules you create (for executing operations, merging context, upserting entity state, confirmed writes to dedicated tables) will be imported by every future workflow file. Design them for reuse, not just for this workflow.

5. **No blueprints.** This workflow does not read from the `blueprints` or `blueprint_steps` tables. The step sequence is explicit in the workflow file.

6. **Entity writes follow `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`.** Read that file before designing the entity persistence approach.

7. **Deploy protocol applies.** This directive does not include deployment, but the workflow must be compatible with the deploy protocol: Railway first, Trigger.dev second. The workflow calls FastAPI internal endpoints that must exist before the workflow runs.

---

## Available Company Enrichment Operations

These are the operations available via `POST /api/v1/execute` that are relevant to company enrichment. You decide which to include and in what order based on what produces a useful enriched company entity.

**Production-proven (used with real data, low failure rates):**
- `company.enrich.profile` — multi-provider waterfall (Prospeo, BlitzAPI, CompanyEnrich, LeadMagic)
- `company.enrich.profile_blitzapi` — single-provider BlitzAPI enrichment (420 production calls, 0% failure)
- `company.research.infer_linkedin_url` — HQ Gemini LinkedIn URL inference (426 calls, 9.6% failure)
- `company.enrich.card_revenue` — Enigma card revenue analytics (10 calls, 20% failure)

**Available but never used in production:**
- `company.enrich.technographics` — LeadMagic technographics
- `company.enrich.tech_stack` — TheirStack job-posting-derived tech stack
- `company.enrich.hiring_signals` — TheirStack hiring signals
- `company.enrich.locations` — Enigma operating locations
- `company.enrich.ecommerce` — StoreLeads ecommerce data

You decide which operations produce a meaningfully enriched company entity for a general-purpose enrichment workflow. Not every operation needs to be included — pick the ones that make a useful default enrichment pass.

---

## Internal Endpoints Available

The workflow will call these FastAPI endpoints (all exist, no new endpoints needed):

- `POST /api/v1/execute` — execute an operation (returns canonical output + provider attempts)
- `POST /api/internal/entity-state/upsert` — upsert entity state (company, person, or job)
- `POST /api/internal/entity-timeline/record-step-event` — record timeline events
- `POST /api/internal/pipeline-runs/update-status` — update pipeline run status
- `POST /api/internal/step-results/update` — update step result status

---

## Existing Code to Read Before Starting

- `CLAUDE.md` — project conventions, auth model, deploy protocol
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — current architecture, known problems (especially sections 1 and 7)
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — entity write rules
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — which operations are production-proven and their reliability
- `trigger/src/tasks/run-pipeline.ts` — the thing you are replacing. Study how it calls FastAPI, merges context, upserts entity state, and handles the Trigger.dev task lifecycle. Extract the patterns worth keeping; discard the problems documented in the architecture doc.
- `trigger/src/utils/` — existing utility modules (condition evaluator lives here)
- `trigger/trigger.config.ts` — how tasks are registered
- `app/routers/internal.py` — the internal endpoints your workflow will call
- `app/routers/execute_v1.py` — the execute endpoint, including `SUPPORTED_OPERATION_IDS` and the request/response shape
- `app/services/entity_state.py` — entity upsert logic and identity resolution (understand what FastAPI already handles so you don't duplicate it)

---

## Deliverable 1: Shared Workflow Utility Modules

Create reusable utility modules under `trigger/src/`. You decide the file structure and module boundaries. The following capabilities must be available as importable functions for any workflow file:

- **Execute an operation** via `POST /api/v1/execute` and return a structured result. Handle HTTP errors, timeouts, and non-success responses.
- **Merge step output** into cumulative context (the shallow-merge pattern used today).
- **Upsert entity state** via `POST /api/internal/entity-state/upsert` with confirmed success. The caller must know whether the write succeeded or failed.
- **Write to dedicated tables** via internal endpoints with confirmed success. Same confirmation requirement as entity state.
- **Internal HTTP client** that handles the auth headers (`Authorization`, `x-internal-org-id`, `x-internal-company-id`) and base URL configuration.

Commit standalone.

---

## Deliverable 2: Company Enrichment Workflow Task

Create a new Trigger.dev task in `trigger/src/tasks/` that enriches a company end-to-end.

**Input:** At minimum, a company domain plus org/company context for auth. You decide the full input shape.

**Behavior:** Execute a sequence of enrichment operations, merge outputs into cumulative context, and persist the enriched entity state. The step sequence, which operations to include, and the error handling approach (fail-fast vs. continue-and-report) are your engineering decisions.

**Persistence:** Entity state must be upserted with confirmed writes using the shared utilities from Deliverable 1.

**Lineage:** The workflow should create or update `pipeline_runs` and `step_results` records so execution is traceable through the same lineage model the rest of the system uses. Study how `run-pipeline.ts` manages these today.

Commit standalone.

---

## Deliverable 3: Tests

Write tests that verify:
- The shared utilities handle success, failure, and timeout cases
- The workflow task executes steps in order and merges context correctly
- Entity state persistence is confirmed (not fire-and-forget)
- A failed persistence write is surfaced, not swallowed

Mock all HTTP calls. Do not call production.

Commit standalone.

---

## What is NOT in scope

- No modifications to `run-pipeline.ts`
- No modifications to FastAPI endpoints (use existing internal endpoints as-is)
- No database migrations
- No deploy commands
- No blueprint or submission flow changes (how this workflow gets triggered from the API layer is a future directive)
- No fan-out logic (this is a single-entity enrichment workflow)
- No dedicated-table auto-persist for this workflow (entity state upsert is sufficient for the enrichment use case; dedicated table patterns will be exercised by subsequent workflows that produce table-specific output like ICP titles or customer lists)

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

This directive does not include deployment. When this work is eventually deployed: Railway first (wait for it to be live), Trigger.dev second. The workflow calls FastAPI internal endpoints that must exist before the workflow runs.

## When done

Report back with:
(a) Shared utility module file paths and the public API surface of each module (function names, signatures)
(b) Which operations you included in the workflow and why
(c) The error handling approach you chose and the rationale
(d) How entity state persistence confirmation works (what happens on write success vs. write failure)
(e) How lineage tracking works (pipeline_runs / step_results integration)
(f) Test count and what they cover
(g) Anything to flag — design decisions that have downstream implications for future workflows
