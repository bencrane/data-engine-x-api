# Directive: Dedicated Job Posting Discovery Workflow

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** This workflow is the TheirStack entry point for job-led discovery. It should follow the same architecture as the dedicated TAM building workflow, but swap the top-of-funnel search step from `company.search.blitzapi` to `job.search`, then drive the same downstream company enrichment and person search/enrichment path through the existing DB-backed child pipeline creation endpoint and router. Production truth to protect: `job.search` already exists, has been called once in production with `0%` failure, and TheirStack job results already include embedded company context, so this workflow must not add an unnecessary company-resolution hop before fan-out.

---

## TheirStack Job Search API

**Primary endpoint:** `POST https://api.theirstack.com/v1/jobs/search`

**Auth:** `Authorization: Bearer <token>`

**Key contract details from the in-repo TheirStack docs:**

- The endpoint requires at least one of:
  - `posted_at_max_age_days`
  - `posted_at_gte`
  - `posted_at_lte`
  - `company_domain_or`
  - `company_linkedin_url_or`
  - `company_name_or`
- Pagination may be page-based or offset-based. The endpoint also accepts `cursor`, but you must choose a single deterministic pagination strategy for this workflow and implement it consistently.
- `include_total_results` is supported but slows responses; use it only if it materially improves workflow behavior or observability.
- Each returned job consumes one TheirStack API credit.
- TheirStack documents `HTTP 429` rate limiting and expects clients to retry with exponential backoff.
- TheirStack explicitly documents duplicate-avoidance patterns using `discovered_at_gte` and `job_id_not`; do not invent a conflicting dedup strategy if the workflow supports repeated or incremental runs.

**Important response fields available in job results:**

- top-level job fields such as `id`, `job_title`, `url`, `final_url`, `source_url`, `date_posted`, `discovered_at`, `description`, `remote`, `seniority`
- top-level company fields such as `company`, `company_domain`
- embedded `company_object` including `name`, `domain`, `linkedin_url`, `industry`, `employee_count`, `long_description`, funding metadata, and technology metadata
- embedded `hiring_team` with `full_name`, `first_name`, `linkedin_url`, and `role`
- response `metadata` including `total_results` and `total_companies`

**TheirStack API documentation to read before building:**

- `docs/api-reference-docs/theirstack/02-search-endpoints/01-job-search.md`
- `docs/api-reference-docs/theirstack/01-general/03-authentication.md`
- `docs/api-reference-docs/theirstack/01-general/04-pagination.md`
- `docs/api-reference-docs/theirstack/01-general/05-rate-limit.md`
- `docs/api-reference-docs/theirstack/01-general/08-avoid-getting-same-job-twice.md`
- `docs/api-reference-docs/theirstack/openapi.json`

---

## Existing code to read

- `CLAUDE.md` — project conventions, chief-agent constraints, production state, auth model, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — non-negotiable build rules
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — current architecture and known problems
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — entity and persistence rules
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — confirms `job.search` has 1 production call with 0% failure and that dedicated workflow migration is in progress
- `docs/EXECUTOR_DIRECTIVE_DEDICATED_TAM_BUILDING_WORKFLOW.md` — closest reference; follow its pagination, batching, child-run creation, and lineage patterns where applicable
- `docs/EXECUTOR_DIRECTIVE_FANOUT_ROUTER_TASK.md` — the router contract you must reuse rather than bypass
- `app/providers/theirstack.py` — `search_jobs(...)` provider adapter and mapped response shape
- `app/services/theirstack_operations.py` — `execute_job_search(...)` service behavior, input extraction, and supported filters
- `app/contracts/theirstack.py` — `TheirStackJobSearchExtendedOutput`, `TheirStackJobItem`, embedded company and hiring-team models
- `app/routers/execute_v1.py` — `job.search` wiring and `SUPPORTED_OPERATION_IDS`
- `app/routers/internal.py` — internal pipeline-run and fan-out endpoints; understand the existing child-run creation path you must reuse
- `app/services/submission_flow.py` — existing submission/run creation patterns and Trigger wiring
- `trigger/src/tasks/tam-building.ts`
- `trigger/src/workflows/tam-building.ts`
- `trigger/src/tasks/company-enrichment.ts`
- `trigger/src/workflows/company-enrichment.ts`
- `trigger/src/tasks/person-search-enrichment.ts`
- `trigger/src/workflows/person-search-enrichment.ts`
- `trigger/src/tasks/pipeline-run-router.ts`
- `trigger/src/workflows/pipeline-run-router.ts`
- `trigger/src/workflows/internal-api.ts`
- `trigger/src/workflows/context.ts`
- `trigger/src/workflows/lineage.ts`
- `trigger/src/workflows/operations.ts`
- `trigger/src/workflows/persistence.ts`

---

### Deliverable 1: Dedicated Job Posting Discovery Workflow Task

Create a dedicated Trigger.dev task entrypoint in `trigger/src/tasks/job-posting-discovery.ts` and a dedicated workflow module in `trigger/src/workflows/job-posting-discovery.ts`.

This workflow is the job-led analog of TAM building. It must:

- call `POST /api/v1/execute` with operation ID `job.search`, not `company.search.blitzapi`
- paginate through all matching job-search results using the existing `job.search` contract and a single deterministic pagination strategy
- preserve job-level lineage and output context for each discovered posting, including at minimum:
  - job identifiers
  - company identifiers present in the result
  - job URLs
  - posting/discovery timestamps
  - hiring-team data when present
- use the embedded TheirStack company context from the job result as the downstream company seed; do not add an extra company resolution step before fan-out
- reuse the existing DB-backed child pipeline creation path and existing router task for downstream orchestration
- create downstream child runs for the existing dedicated company enrichment workflow and, from there or through the established chained path, the existing dedicated person search/enrichment workflow
- keep the downstream path aligned with TAM building rather than inventing a second orchestration mechanism

Additional requirements:

- Keep Trigger code schema-agnostic. Do not hardcode `public`, `ops`, or `entities` in Trigger workflow code.
- Do not bypass the router by directly wiring an ad hoc task-to-task path unless the current TAM implementation already does so and you can justify that it is the same lineage-preserving pattern. If the current TAM implementation and the router directive are materially inconsistent, stop and report the inconsistency instead of inventing a third pattern.
- Use bounded concurrency and backpressure appropriate to TheirStack rate limits and the scale of downstream child-run creation.
- Handle `HTTP 429` and transient search-page failures explicitly. Silent page loss is not acceptable.
- If the current workflow utilities can be cleanly reused as-is, reuse them. If a small shared utility extraction is needed to avoid duplicating TAM pagination or child-run creation logic, keep it tightly scoped to that reuse objective.
- Because `job` is one of the locked entity types in this system, preserve a clean path for job-posting identity and lineage. If the existing `POST /api/internal/entity-state/upsert` path already cleanly supports job postings for this workflow, use it with confirmed writes. If it does not cleanly support this workflow, stop and report the gap rather than inventing a parallel persistence mechanism.
- Preserve the ability to pass through or support TheirStack’s duplicate-avoidance filters (`discovered_at_gte`, `job_id_not`) if the workflow is later used in repeated discovery runs.

**Input:** At minimum, job-search criteria plus org/company auth context. You decide the full input shape, but it must support real job-led discovery use cases built from role/title filters, keyword/description filters, geographic filters, and date-window filters.

**Behavior:** Search jobs, paginate fully, materialize job-level workflow context, and fan out into the existing downstream dedicated workflows through the generic child-run path and router.

Commit standalone.

### Deliverable 2: Tests

Add or update tests to verify:

- multi-page `job.search` pagination collects the full result set
- the workflow uses the existing `job.search` operation contract rather than calling TheirStack directly from Trigger
- `HTTP 429` or transient page failures are handled explicitly and do not silently truncate the result set
- embedded company context from TheirStack job results is used as the downstream company seed
- the workflow creates downstream child runs through the existing generic child pipeline creation endpoint and router path
- lineage is traceable from the job-posting discovery workflow to company-enrichment and person-search child runs
- empty search results are handled as a clean no-results outcome, not as a workflow failure
- if job entity persistence is supported in-scope, the write is confirmed and not fire-and-forget

Mock all HTTP calls and Trigger.dev SDK calls. Do not call production or TheirStack.

Commit standalone.

---

**What is NOT in scope:** No modifications to `trigger/src/tasks/run-pipeline.ts`. No new provider adapters for TheirStack job search. No new FastAPI public API endpoints. No new database migrations. No bespoke downstream workflow path that bypasses the existing router and generic child-run creation mechanism. No deploy commands. No changes to the company enrichment or person search/enrichment workflow behavior beyond minimal input-contract adjustments that are strictly required to accept the existing routed child payload shape. No new dedicated tables for job postings.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the task file path and workflow module path, (b) the exact pagination strategy chosen and why, (c) how `HTTP 429` and partial-page failures are handled, (d) how job-level context is preserved, including which job/company fields are carried forward, (e) how downstream child runs are created and how the router is involved, (f) whether existing TAM-building code was reused directly or via a small shared extraction, (g) whether job entity persistence was implemented through the existing confirmed-write path or blocked by a real gap, (h) test count and what each test covers, (i) anything to flag — scale concerns, input-contract mismatches, router assumptions, or dedup/incremental-run considerations.
