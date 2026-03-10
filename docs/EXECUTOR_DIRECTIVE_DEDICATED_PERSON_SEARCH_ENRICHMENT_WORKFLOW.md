# Directive: Priority 3 — Second Dedicated Workflow File (Person Search/Enrichment)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The company enrichment workflow and shared utility modules are built (Priority 2). The schema split into `ops` and `entities` is complete (Priority 4). This is the second dedicated workflow: person search and enrichment. Almost every outbound use case requires enriched people with verified contact info. This workflow takes a company domain (or enriched company context from a prior company enrichment run) as input, finds people at that company, and enriches them with contact information.

This workflow produces multiple person entities from a single company input — one company yields N people. How to handle that fan-out (sequential loop, parallel execution, child tasks) is an engineering decision for you to make.

---

## The Problem

A company domain goes in. Enriched person entities with contact information come out. The workflow must:
1. Search for people at the company
2. Enrich each discovered person (profile data, contact info)
3. Persist each person to entity state in the `entities` schema with confirmed writes

---

## Architectural Constraints

1. **New Trigger.dev task in `trigger/src/tasks/`.** Does NOT modify `run-pipeline.ts`.

2. **Use the shared utility modules from Priority 2.** Execute operations, merge context, upsert entity state, confirmed writes — all through the existing shared utilities. If the utilities need extension to support person entities or fan-out patterns, extend them. Do not duplicate them.

3. **Write to the `entities` schema.** Entity state upserts go through `POST /api/internal/entity-state/upsert`, which now writes to `entities.person_entities`. The workflow calls FastAPI endpoints — FastAPI handles schema-qualified queries.

4. **FastAPI still owns all database writes.** Same runtime boundary as the company enrichment workflow.

5. **Internal auth model:** `Authorization: Bearer <INTERNAL_API_KEY>` with `x-internal-org-id` and `x-internal-company-id` headers.

6. **Confirmed writes, not fire-and-forget.** Same pattern as the company enrichment workflow. Every entity state write must be confirmed. Write failures must be surfaced, not swallowed.

7. **Fan-out is a first-class concern.** One company produces multiple people. The workflow must handle this cleanly — the executor decides the concurrency model, error isolation (does one failed person enrichment fail the whole workflow?), and how results are aggregated.

8. **Entity identity resolution for persons is handled by FastAPI.** The `entity_state.py` service uses deterministic UUIDv5 from natural keys (LinkedIn URL is the primary key for person identity). The workflow does not need to implement identity resolution — it passes the data to the upsert endpoint.

9. **Deploy protocol applies.** This directive does not include deployment. When deployed: Railway first, Trigger.dev second.

---

## Available Person Operations

These are the operations available via `POST /api/v1/execute` relevant to person search and enrichment. You decide which to include and in what order.

**Person search (find people at a company):**
- `person.search` — multi-provider waterfall (Prospeo, BlitzAPI Employee Finder + Waterfall ICP, CompanyEnrich, LeadMagic Employee Finder + Role Finder). 5 production calls, 0% failure.
- `person.search.employee_finder_blitzapi` — dedicated BlitzAPI employee search with level/function/location filters. Never used in production.
- `person.search.waterfall_icp_blitzapi` — dedicated BlitzAPI cascade ICP search with tier matching. Never used in production.

**Person enrichment (enrich a discovered person):**
- `person.enrich.profile` — Prospeo → AmpleLeads (if include_work_history) → LeadMagic. 1 production call, 0% failure.

**Contact resolution (get email/phone for a person):**
- `person.contact.resolve_email` — LeadMagic → Icypeas → Parallel. 27 production calls, 0% failure.
- `person.contact.resolve_email_blitzapi` — dedicated BlitzAPI work email finder from LinkedIn URL. Never used in production.
- `person.contact.verify_email` — MillionVerifier → Reoon. Never used in production.
- `person.contact.resolve_mobile_phone` — LeadMagic → BlitzAPI. Never used in production.

You decide which combination produces a useful enriched person with verified contact info for a general-purpose outbound workflow.

---

## Internal Endpoints Available

Same endpoints as the company enrichment workflow (all exist, no new endpoints needed):

- `POST /api/v1/execute` — execute an operation
- `POST /api/internal/entity-state/upsert` — upsert entity state (supports `person` entity type)
- `POST /api/internal/entity-timeline/record-step-event` — record timeline events
- `POST /api/internal/pipeline-runs/update-status` — update pipeline run status
- `POST /api/internal/step-results/update` — update step result status

---

## Existing Code to Read Before Starting

- `CLAUDE.md` — project conventions, auth model, deploy protocol
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — architecture, known problems
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — entity write rules
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — which operations are production-proven
- `trigger/src/tasks/` — the company enrichment workflow from Priority 2 (follow the same patterns)
- `trigger/src/` — the shared utility modules from Priority 2 (import and extend these)
- `trigger/src/tasks/run-pipeline.ts` — reference for how fan-out and person entity handling work in the current system
- `app/services/entity_state.py` — person entity identity resolution (LinkedIn URL as primary natural key)
- `app/routers/execute_v1.py` — the execute endpoint and `SUPPORTED_OPERATION_IDS`
- `app/routers/internal.py` — internal endpoints

---

## Deliverable 1: Extend Shared Utilities (if needed)

If the shared utility modules from Priority 2 need extension to support person entity workflows or fan-out patterns, make those changes here. If no extensions are needed, skip this deliverable and note that in your report.

Do not duplicate utility code. Extend the existing modules.

Commit standalone.

---

## Deliverable 2: Person Search/Enrichment Workflow Task

Create a new Trigger.dev task in `trigger/src/tasks/` that finds and enriches people at a company.

**Input:** At minimum, a company domain plus org/company context for auth. May also accept enriched company context from a prior company enrichment run (e.g., LinkedIn URL, company name). You decide the full input shape.

**Behavior:**
- Search for people at the company
- For each discovered person: enrich profile, resolve contact info
- Persist each person to entity state with confirmed writes
- Track lineage through `pipeline_runs` and `step_results`

The step sequence, which operations to include, fan-out concurrency model, and error handling approach are your engineering decisions.

Commit standalone.

---

## Deliverable 3: Tests

Write tests that verify:
- The workflow discovers people and fans out enrichment correctly
- Each person entity is persisted with confirmed writes
- Fan-out error isolation works as designed (one failed person does not silently corrupt the rest)
- The shared utilities (including any extensions from Deliverable 1) handle person entity types correctly

Mock all HTTP calls. Do not call production.

Commit standalone.

---

## What is NOT in scope

- No modifications to `run-pipeline.ts`
- No modifications to FastAPI endpoints (use existing internal endpoints as-is)
- No database migrations
- No deploy commands
- No changes to the company enrichment workflow (unless a shared utility extension requires a compatible change)
- No dedicated-table writes (e.g., `salesnav_prospects`) — entity state upsert is sufficient for this workflow; dedicated table persistence for specific person output types is a future directive
- No blueprint or submission flow changes

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

When this work is eventually deployed: Railway first (wait for it to be live), Trigger.dev second. The workflow calls FastAPI internal endpoints that must exist before the workflow runs.

## When done

Report back with:
(a) Whether shared utilities were extended and what was added
(b) Which operations you included in the workflow and why
(c) The fan-out approach — how the workflow handles one-company-to-many-people, concurrency model, and error isolation
(d) The error handling approach and rationale (fail-fast vs. continue-on-error per person)
(e) How entity state persistence confirmation works for person entities
(f) How lineage tracking works across the fan-out (pipeline_runs / step_results for parent and per-person)
(g) Test count and what they cover
(h) Anything to flag — design decisions with downstream implications for future workflows, utility API changes that affect the company enrichment workflow
