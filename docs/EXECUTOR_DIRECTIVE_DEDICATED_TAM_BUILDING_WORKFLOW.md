# Directive: Dedicated TAM Building Workflow

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** This is the first revenue-critical workflow. When a new GTMDirect client is onboarded, their target addressable market (TAM) needs to be populated. The workflow takes client-defined company search criteria, searches for all matching companies via BlitzAPI Find Companies, then for each found company runs the existing company enrichment and person search/enrichment workflows.

The company search step is new. The enrichment and person search steps already exist as dedicated workflows. This workflow is an orchestrator — its primary job is search with full pagination and fan-out into the existing workflows.

---

## The Problem

Client search criteria go in. A fully populated TAM comes out — enriched companies with enriched, contact-resolved people. The workflow must:

1. Search BlitzAPI Find Companies with the client's criteria, paginating through all results (not just the first page)
2. For each discovered company, run the company enrichment workflow
3. For each enriched company, run the person search/enrichment workflow
4. Track lineage across the entire chain so the client can see what was found, what was enriched, and what failed

---

## Key Design Decisions

These are the hard problems in this workflow. The directive does not prescribe solutions — the executor makes these engineering decisions.

**Pagination:** BlitzAPI Find Companies returns a maximum of 50 results per page with a cursor-based pagination token. A TAM search may match hundreds or thousands of companies. The workflow must paginate through all pages to get the complete result set. How to handle this — eager collection before fan-out, streaming page-by-page into fan-out, error handling on partial pagination failure — is your decision.

**Fan-out scale:** One TAM search can produce hundreds of companies, each of which needs enrichment and person search. This is a much larger fan-out surface than any previous workflow. How to manage concurrency, backpressure, and partial failure across potentially hundreds of downstream workflow invocations is your decision.

**Workflow chaining:** The company enrichment and person search/enrichment workflows already exist as dedicated Trigger.dev tasks. This workflow needs to invoke them for each discovered company. Whether to invoke them directly (task-to-task), through the fan-out router, through DB-backed fan-out via FastAPI, or through another mechanism is your decision. Consider lineage tracking, retry granularity, and observability when choosing.

---

## Architectural Constraints

1. **New Trigger.dev task in `trigger/src/tasks/`.** Does NOT modify `run-pipeline.ts`.

2. **Use the shared utility modules.** Internal HTTP client, confirmed writes, context merge — all through the existing shared utilities.

3. **BlitzAPI Find Companies is called via `POST /api/v1/execute` with operation ID `company.search.blitzapi`.** This operation exists in the code catalog but has never been called in production. Read the provider adapter and the BlitzAPI API documentation to understand the request/response shape, pagination contract, and available filters.

4. **The downstream workflows (company enrichment, person search/enrichment) are existing Trigger.dev tasks.** They have defined input contracts. Read their source to understand what they expect.

5. **Lineage must span the full chain.** The TAM build is one logical unit of work. The parent submission, the search phase, the per-company enrichment, and the per-company person search should all be traceable. How deeply this integrates with `pipeline_runs` and `step_results` is your decision, but the operator must be able to answer "what happened for this TAM build" from the ops tables.

6. **Entity writes go through the downstream workflows.** This workflow does not write entity state directly — it orchestrates workflows that do. The confirmed-write contract is enforced by the downstream workflows.

7. **Deploy protocol applies.** When deployed: Railway first, Trigger.dev second (standard order — no reversal needed here since this workflow calls FastAPI endpoints that already exist).

---

## BlitzAPI Find Companies API

**The executor must read the BlitzAPI provider adapter and API documentation:**

- `app/providers/blitzapi.py` — the existing BlitzAPI provider adapter. Look for the company search function and understand its request/response mapping.
- `app/services/` — the service function for `company.search.blitzapi`. Understand how it wraps the provider adapter.
- `app/routers/execute_v1.py` — how `company.search.blitzapi` is dispatched.
- BlitzAPI API documentation: `https://docs.blitzapi.com/reference/find-companies` — read the full API reference for the Find Companies endpoint, including pagination, filters, and response shape.

Key facts about the BlitzAPI Find Companies endpoint:
- Maximum 50 results per page
- Cursor-based pagination (response includes a cursor token for the next page)
- Supports filters: keyword, industry, location, employee count range, company type, founded year range
- The existing `company.search.blitzapi` operation may already handle single-page requests — the executor must determine whether pagination is already supported or needs to be added

---

## Existing Code to Read Before Starting

- `CLAUDE.md` — project conventions, auth model, deploy protocol
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — `company.search.blitzapi` has never been called in production (section 3, never-called operations list)
- `app/providers/blitzapi.py` — BlitzAPI provider adapter (company search function)
- `app/routers/execute_v1.py` — operation dispatch for `company.search.blitzapi`
- `trigger/src/tasks/` — the company enrichment workflow and person search/enrichment workflow (understand their input contracts)
- `trigger/src/tasks/` — the fan-out router task (if chaining through it)
- `trigger/src/` — shared utility modules
- BlitzAPI API docs: `https://docs.blitzapi.com/reference/find-companies`

---

## Deliverable 1: TAM Building Workflow Task

Create a new Trigger.dev task in `trigger/src/tasks/` that builds a TAM from client search criteria.

**Input:** Client-defined search criteria (the filters for BlitzAPI Find Companies) plus org/company context for auth. You decide the full input shape.

**Behavior:**
- Execute `company.search.blitzapi` with the provided criteria, paginating through all result pages
- For each discovered company, invoke the company enrichment workflow
- For each enriched company, invoke the person search/enrichment workflow
- Track lineage across the full chain

The pagination strategy, fan-out concurrency model, workflow chaining mechanism, and error handling approach are your engineering decisions. The workflow must handle the scale implied by TAM building — potentially hundreds of companies.

Commit standalone.

---

## Deliverable 2: Tests

Write tests that verify:
- Pagination collects all results across multiple pages (mock a multi-page BlitzAPI response)
- Fan-out invokes the downstream workflows for each discovered company
- Partial failure in downstream workflows does not silently corrupt the rest of the TAM build
- Lineage is traceable from the TAM build through to individual company/person enrichment
- Empty search results are handled cleanly (zero companies found is a valid outcome, not an error)

Mock all HTTP calls and Trigger.dev SDK calls. Do not call production or BlitzAPI.

Commit standalone.

---

## What is NOT in scope

- No modifications to `run-pipeline.ts`
- No modifications to the company enrichment or person search/enrichment workflows (unless a minor input contract adjustment is needed — if so, keep it minimal and report it)
- No modifications to FastAPI endpoints
- No database migrations
- No deploy commands
- No ICP job titles, intel briefings, or other downstream enrichment beyond company profile and person contact resolution
- No client onboarding UI or API — this is the workflow engine only

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

When this work is eventually deployed: Railway first (wait for it to be live), Trigger.dev second. Standard order — no reversal needed.

## When done

Report back with:
(a) The pagination strategy — how the workflow collects all pages and what happens on partial pagination failure
(b) The fan-out approach — concurrency model, how hundreds of companies are processed, backpressure or batching strategy if any
(c) The workflow chaining mechanism — how the TAM workflow invokes company enrichment and person search (direct task invocation, router, DB-backed fan-out, or other)
(d) How lineage works across the chain — can the operator trace from TAM build → company enrichment → person search for a single company?
(e) The input shape — what search criteria fields are supported
(f) Whether `company.search.blitzapi` already supports pagination or whether you needed to add/extend it
(g) Test count and what they cover
(h) Anything to flag — scale concerns, rate limiting considerations, BlitzAPI API limitations discovered, downstream workflow input contract changes needed
