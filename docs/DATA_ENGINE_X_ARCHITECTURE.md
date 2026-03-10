# data-engine-x: Architecture, Execution Model & Known Problems

Last updated: 2026-03-10

---

## 1. What data-engine-x Is

data-engine-x is a multi-tenant enrichment backend. It accepts batch requests containing entities (companies, persons, job postings), runs them through configurable multi-step pipelines backed by 20+ external providers, and persists both raw provider output and canonical entity intelligence.

Two runtimes work together:

| Runtime | Language | Responsibility |
|---------|----------|----------------|
| **FastAPI** | Python | Auth, API contracts, DB reads/writes, operation execution (provider calls), internal callbacks |
| **Trigger.dev** | TypeScript | Pipeline orchestration: step sequencing, condition evaluation, output chaining, fan-out, long-polling for async providers |

The boundary between them is internal HTTP. Trigger.dev calls FastAPI for everything that touches the database or executes provider operations (with 4 exceptions — the Parallel.ai direct operations).

---

## 2. The Complete Request Lifecycle

### 2.1 Batch Submission (the primary entry point)

```
Client → POST /api/v1/batch/submit
         ├─ Auth resolution (JWT, API token, or super-admin key)
         ├─ Validates blueprint_id exists for this org
         ├─ Creates a Submission row
         ├─ For each entity in the request:
         │   ├─ Creates a Pipeline Run row (with blueprint_snapshot frozen at creation time)
         │   ├─ Creates Step Result placeholder rows (one per blueprint step, status="pending")
         │   └─ HTTP POST to Trigger.dev API → triggers "run-pipeline" task
         │       └─ Stores returned trigger_run_id on the pipeline_run row
         └─ Returns submission_id + list of pipeline_run_ids
```

**Key detail:** The blueprint is snapshotted at submission time. If the blueprint changes later, in-flight runs use the frozen snapshot. This is correct behavior but means there's no way to "upgrade" running pipelines.

### 2.2 Pipeline Execution (Trigger.dev side)

```
run-pipeline task starts
  ├─ Fetches pipeline run details via POST /api/internal/pipeline-runs/get
  ├─ Sets pipeline run status to "running"
  ├─ Syncs submission status
  ├─ Determines execution start position:
  │   ├─ For fan-out child runs: start_from_position (skips parent's earlier steps)
  │   └─ For root runs: position 1
  │
  ├─ Builds initial cumulative_context from blueprint entity input or submission input
  │
  └─ FOR EACH STEP (in position order):
      ├─ 1. Condition evaluation
      │   └─ Evaluates step condition against cumulative_context
      │       Supports: exists, eq, ne, lt, gt, lte, gte, contains, icontains, in
      │       Plus all/any logical groups
      │   └─ If condition not met → skip step (and all downstream if fan_out step)
      │
      ├─ 2. Freshness check (if skip_if_fresh configured)
      │   └─ Calls /api/internal/entity-state/check-freshness
      │   └─ If entity is fresh → skip step, merge cached canonical_payload into context
      │
      ├─ 3. Operation execution (one of two paths):
      │   ├─ Path A: 4 Parallel.ai operations run DIRECTLY from Trigger.dev
      │   │   ├─ company.derive.icp_job_titles
      │   │   ├─ company.derive.intel_briefing
      │   │   ├─ person.derive.intel_briefing
      │   │   └─ company.resolve.domain_from_name_parallel
      │   │   (These use Trigger.dev's wait.for() for long-polling)
      │   │
      │   └─ Path B: All other operations → HTTP POST /api/v1/execute
      │       └─ FastAPI dispatches to the appropriate provider adapter
      │
      ├─ 4. Auto-persist to dedicated tables (try/catch, non-blocking)
      │   └─ Operation-specific: ICP job titles, intel briefings, company customers,
      │      Gemini ICP titles, ads (LinkedIn/Meta/Google), Sales Nav prospects
      │
      ├─ 5. Output chaining
      │   └─ result.output is shallow-merged into cumulative_context
      │   └─ Next step receives the merged context as its input
      │
      ├─ 6. Fan-out (if step has fan_out: true)
      │   └─ Extracts "results" array from operation output
      │   └─ Calls /api/internal/pipeline-runs/fan-out
      │       └─ Creates child pipeline runs (one per result entity)
      │       └─ Each child run starts from position N+1 (after the fan-out step)
      │       └─ Deduplicates by identity tokens (domain, LinkedIn URL, email)
      │   └─ Parent run marks as succeeded and returns
      │
      └─ 7. Fail-fast behavior
          └─ If ANY step fails → mark remaining steps as "skipped"
          └─ Mark pipeline run as "failed"
          └─ Sync submission status
          └─ Return immediately (no partial success)

  AFTER ALL STEPS SUCCEED:
    ├─ Mark pipeline run as "succeeded"
    ├─ Upsert entity state (canonical entity record)
    └─ Sync submission status
```

### 2.3 Operation Execution (FastAPI side)

The `/api/v1/execute` endpoint is a giant dispatch router. It:

1. Validates the operation_id is in SUPPORTED_OPERATION_IDS (80+ operations)
2. Validates entity_type matches operation prefix (person.* requires person, etc.)
3. Dispatches to the matching service function
4. Each service function calls one or more provider adapters
5. Returns a canonical response: `{ run_id, operation_id, status, output, provider_attempts }`

**Provider adapter pattern:**
- Each provider has its own module under `app/providers/`
- Service functions in `app/services/` orchestrate provider waterfalls (try provider A, fall back to B)
- Provider attempts are logged with raw payloads for audit
- Operation execution history is persisted to `operation_runs` and `operation_attempts` tables

### 2.4 Entity State Accumulation

After a pipeline run succeeds, Trigger.dev calls `/api/internal/entity-state/upsert`:

1. Extracts identity fields from cumulative_context (domain for companies, linkedin_url for persons)
2. Performs identity resolution (find-or-create by identity)
3. Merges new fields into the canonical entity record
4. Increments `record_version` (stale-write protection)
5. Records timeline events for the entity

Entity tables: `company_entities`, `person_entities`, `job_posting_entities`

### 2.5 Status Polling

```
Client → POST /api/v1/batch/status { submission_id }
         ├─ Fetches submission record
         ├─ Fetches all pipeline runs for this submission
         ├─ Aggregates status (pending/running/succeeded/failed/partial)
         └─ Returns per-entity results with step-level detail
```

---

## 3. The Trigger.dev <-> FastAPI Boundary

### 3.1 How Trigger.dev is invoked

FastAPI triggers Trigger.dev via HTTP POST to the Trigger.dev API:

```python
# app/services/trigger.py
POST {TRIGGER_API_URL}/api/v1/tasks/run-pipeline/trigger
Headers: Authorization: Bearer {TRIGGER_SECRET_KEY}
Body: { payload: { pipeline_run_id, org_id, company_id, api_url, internal_api_key } }
```

The `api_url` and `internal_api_key` are passed IN the payload so Trigger.dev knows how to call back. This is a design choice — env vars (`DATA_ENGINE_API_URL`, `DATA_ENGINE_INTERNAL_API_KEY`) serve as fallbacks.

### 3.2 How Trigger.dev calls back to FastAPI

All callbacks use internal auth:
```
Authorization: Bearer {INTERNAL_API_KEY}
x-internal-org-id: {org_uuid}
x-internal-company-id: {company_uuid}  (optional)
```

Internal endpoints called by Trigger.dev:

| Endpoint | Purpose |
|----------|---------|
| `/api/internal/pipeline-runs/get` | Fetch run details + blueprint snapshot |
| `/api/internal/pipeline-runs/update-status` | Mark run as running/succeeded/failed |
| `/api/internal/pipeline-runs/fan-out` | Create child runs from fan-out results |
| `/api/internal/step-results/update` | Update step status + output payload |
| `/api/internal/step-results/mark-remaining-skipped` | Bulk-skip downstream steps on failure |
| `/api/internal/submissions/sync-status` | Recalculate submission aggregate status |
| `/api/internal/entity-state/upsert` | Persist canonical entity intelligence |
| `/api/internal/entity-state/check-freshness` | Check if entity was recently enriched |
| `/api/internal/entity-timeline/record-step-event` | Record timeline event per step |
| `/api/internal/entity-relationships/record` | Record entity-to-entity relationships |
| `/api/internal/icp-job-titles/upsert` | Persist ICP job title research |
| `/api/internal/company-intel-briefings/upsert` | Persist company intel briefing |
| `/api/internal/person-intel-briefings/upsert` | Persist person intel briefing |
| `/api/internal/company-customers/upsert` | Persist discovered customers |
| `/api/internal/gemini-icp-job-titles/upsert` | Persist Gemini ICP titles |
| `/api/internal/company-ads/upsert` | Persist ad intelligence |
| `/api/internal/salesnav-prospects/upsert` | Persist Sales Nav prospects |
| `/api/v1/execute` | Execute an operation (via internal auth) |

### 3.3 The 4 Direct Parallel.ai Operations

Four operations bypass FastAPI entirely and run directly from Trigger.dev:

1. **`company.derive.icp_job_titles`** — Deep research for ICP job titles (Parallel.ai "pro" processor, ~30min)
2. **`company.derive.intel_briefing`** — Company intel briefing (Parallel.ai "ultra" processor, ~45min)
3. **`person.derive.intel_briefing`** — Person intel briefing (Parallel.ai "ultra" processor, ~45min)
4. **`company.resolve.domain_from_name_parallel`** — Domain resolution (Parallel.ai "lite" processor, ~12min)

These run directly from Trigger.dev because they're long-running async tasks that benefit from Trigger.dev's `wait.for()` primitive. They poll the Parallel.ai API at intervals (20s-240s) for up to 90-135 attempts.

**The LLM prompts for these operations are hardcoded as string constants in `run-pipeline.ts`.** The ICP job titles prompt alone is ~50 lines. The company and person intel briefing prompts are ~80 lines each, including full JSON output schemas.

---

## 4. Multi-Tenancy & Auth Model

### 4.1 Tenant Hierarchy

```
Org
 └─ Company (many per org)
     └─ User (many per company)
         └─ Roles: org_admin, company_admin, member
```

Execution lineage:
```
Company → Submission → Pipeline Run → Step Result
```

### 4.2 Four Auth Paths

| Path | How it works | Produces |
|------|-------------|----------|
| Tenant JWT session | `decode_tenant_session_jwt()` | `AuthContext` |
| Tenant API token | SHA-256 hash lookup against `api_tokens` table | `AuthContext` |
| Super-admin API key | Compared to `SUPER_ADMIN_API_KEY` env var | `SuperAdminContext` |
| Internal service auth | `Bearer {INTERNAL_API_KEY}` + `x-internal-org-id` header | `AuthContext` (synthesized) |

Super-admin on `/api/v1/execute` requires explicit `org_id` + `company_id` in the request body — the system synthesizes a tenant AuthContext from these.

---

## 5. Database Schema (Key Tables)

### Core Tenancy
- `orgs` — Organizations
- `companies` — Companies within orgs (has `domain` column)
- `users` — Users with company + org membership
- `api_tokens` — Tenant API tokens (SHA-256 hashed)

### Execution Lineage
- `submissions` — Batch submission records
- `pipeline_runs` — Individual entity pipeline executions (has `parent_pipeline_run_id` for fan-out, `blueprint_snapshot` JSONB, `trigger_run_id`)
- `step_results` — Per-step execution records (status, input_payload, output_payload, error_message, duration_ms)
- `operation_runs` — Durable operation execution log
- `operation_attempts` — Individual provider attempts per operation run

### Entity Intelligence
- `company_entities` — Canonical company records (versioned with `record_version`)
- `person_entities` — Canonical person records (versioned)
- `job_posting_entities` — Canonical job posting records
- `entity_timeline` — Per-entity operation audit trail
- `entity_snapshots` — Append-only entity change detection
- `entity_relationships` — Typed, directional entity relationships

### Dedicated Output Tables
- `icp_job_titles` — Parallel.ai ICP job title research output
- `gemini_icp_job_titles` — Gemini ICP job title output
- `company_intel_briefings` — Parallel.ai company intel briefings
- `person_intel_briefings` — Parallel.ai person intel briefings
- `company_customers` — Discovered customer relationships
- `company_ads` — LinkedIn/Meta/Google ad intelligence
- `salesnav_prospects` — Sales Navigator prospect data

### Configuration
- `steps` — Global operation registry (has `executor_config` JSONB)
- `blueprints` — Org-scoped pipeline definitions
- `blueprint_steps` — Steps within a blueprint (position, operation_id, step_config, condition, fan_out, is_enabled)

---

## 6. Blueprints & Pipeline Configuration

A blueprint defines a reusable pipeline. Each blueprint has:
- An `entity_type` (company, person, or job)
- An ordered list of steps, each with:
  - `operation_id` — Which operation to execute
  - `position` — Execution order
  - `condition` — Runtime condition evaluated against cumulative_context
  - `step_config` — Operation-specific parameters
  - `fan_out` — Boolean, whether this step creates child runs from results
  - `is_enabled` — Can disable steps without removing them

### Example: AlumniGTM Company Workflow

```
Step 1: company.research.infer_linkedin_url
Step 2: company.enrich.profile_blitzapi        [condition: exists company_linkedin_url]
Step 3: company.research.icp_job_titles_gemini
Step 4: company.research.discover_customers_gemini
Step 5: company.derive.icp_criterion
Step 6: company.derive.salesnav_url             [condition: exists company_linkedin_id]
```

### Example: Staffing Enrichment (with fan-out)

```
Step 1: job.search                              [fan_out: true, limit=100]
Step 2: job.validate.is_active                  [condition: exists company_domain]
Step 3: company.enrich.profile                  [condition: validation_result in {active, unknown}]
Step 4: person.search                           [fan_out: true, limit=5]
Step 5: person.contact.resolve_email            [condition: exists linkedin_url OR exists work_email]
Step 6: person.contact.verify_email             [condition: exists work_email]
Step 7: person.contact.resolve_mobile_phone     [condition: exists linkedin_url OR exists full_name]
```

Fan-out creates nested child runs — job.search finds 100 jobs, each becomes a child run starting at step 2. person.search within each child finds 5 people, each becomes a grandchild run starting at step 5. A single submission can produce 500+ pipeline runs.

---

## 7. What Is Problematic

### 7.1 The `run-pipeline.ts` File Is a 2,700-Line Monolith

This single file contains:
- 4 complete Parallel.ai operation implementations (each ~240 lines) with hardcoded LLM prompts
- 10+ auto-persist blocks (try/catch for each dedicated table)
- The pipeline orchestration loop
- All helper functions (condition checking, freshness, context merging, fan-out extraction)
- Interface definitions

**Why this is bad:**
- Adding a new Parallel.ai operation or a new dedicated table means modifying this already-massive file
- The 4 Parallel.ai operation functions are 95% identical (create task → poll → fetch result) with only the prompt and field mapping varying — massive code duplication
- Prompt text is embedded as string constants at the top of an orchestration file — prompts should live in a separate config or template system
- Each auto-persist block is a copy-paste pattern with minor field variations

### 7.2 Auto-Persist Pattern Is Fragile and Unscalable

After each operation execution, the pipeline runner checks `if (operationId === "X" && result.status === "found")` and then calls the corresponding internal upsert endpoint inside a try/catch. There are currently **10 separate auto-persist blocks** for:

1. ICP job titles
2. Company intel briefings
3. Person intel briefings
4. Company customers (2 operations share one)
5. Gemini ICP job titles
6. LinkedIn ads
7. Meta ads
8. Google ads
9. Sales Nav prospects

**Problems:**
- Every new dedicated table requires adding another if-block in run-pipeline.ts, deploying Trigger.dev, and potentially missing it during deploy timing issues
- Failures are silently swallowed (by design — you don't want a persistence side-effect to kill a pipeline). But this means data can go missing and you won't notice unless you audit `step_results` vs dedicated tables
- The ICP auto-persist incident (2026-02-25) was caused by deploying Trigger.dev before the Railway endpoint was live — the try/catch logged a warning but the data was lost
- No retry mechanism for failed auto-persists — it's fire-and-forget

### 7.3 Deploy Sequencing Is a Landmine

The deploy protocol is strict: **Railway first, wait 1-2 minutes, then Trigger.dev**. If reversed:

- New Trigger.dev code calls FastAPI endpoints that don't exist yet
- Auto-persist calls fail silently (try/catch swallows errors)
- Pipeline runs "succeed" but data doesn't land in dedicated tables
- The data exists in `step_results.output_payload` but not in the dedicated tables
- Manual backfill scripts are required to recover

This has already caused a production incident. The protocol is documented but relies entirely on human discipline — there's no automated guard.

### 7.4 The `/api/v1/execute` Dispatch Is a 1,300+ Line Giant Switch

`execute_v1.py` is a massive file containing:
- 80+ operation IDs in `SUPPORTED_OPERATION_IDS`
- A single `execute_v1()` function with a long chain of `if/elif` for routing
- Each branch calls a service function, awaits the result, handles status codes

Adding a new operation means:
1. Adding the ID to `SUPPORTED_OPERATION_IDS`
2. Adding an `elif` branch in the dispatch function
3. Importing the new service function

There's no registry pattern, no decorator-based routing, no auto-discovery. It's all manual wiring.

### 7.5 Output Chaining Uses Shallow Merge

```typescript
function mergeContext(current, output) {
  if (!output) return current;
  return { ...current, ...output };
}
```

This is a shallow merge. If two operations produce different nested objects under the same key, the second overwrites the first entirely. There's no deep merge, no conflict detection, no merge logging.

Example: if step 1 returns `{ details: { a: 1 } }` and step 2 returns `{ details: { b: 2 } }`, the cumulative context will have `{ details: { b: 2 } }` — the `a: 1` is lost.

### 7.6 No Retry for Pipeline-Level Operations

The `run-pipeline` task has `retry: { maxAttempts: 1 }` — meaning **no retries**. If a Trigger.dev task crashes (OOM, network partition, Trigger.dev platform issue), the pipeline run is abandoned.

Individual provider calls within FastAPI operations may have their own retry logic, but if the orchestration itself fails, there's no recovery. The `/api/super-admin/pipeline-runs/retry` endpoint exists for manual retry but requires operator intervention.

### 7.7 Parallel.ai Operations Running Inside Trigger.dev Break the Boundary

The stated architecture is: "FastAPI owns all provider calls, Trigger.dev owns orchestration." But 4 Parallel.ai operations break this rule by running directly inside Trigger.dev. This means:

- `PARALLEL_API_KEY` must be configured in Trigger.dev's env vars, not in Doppler/Railway
- Operation execution for these 4 operations is NOT logged in `operation_runs`/`operation_attempts` tables (no audit trail at the operation level — only step_results capture the output)
- If you need to change the prompt or API integration pattern, you must modify TypeScript and deploy Trigger.dev, not Python
- The polling logic (create → poll → fetch result) is duplicated 4 times with nearly identical code

### 7.8 Fan-Out Deduplication Happens at Creation, Not Execution

When a fan-out step produces results, the system creates child runs and deduplicates by identity tokens (domain, LinkedIn URL, email). But:

- Deduplication is only within a single fan-out batch — if the same entity appears in two separate submissions, both will create runs
- There's no cross-submission deduplication
- The dedup relies on identity tokens extracted from the fan-out result, which may not always contain the expected fields

### 7.9 Entity State Upsert Failure Kills the Entire Run

After all steps succeed, Trigger.dev calls `/api/internal/entity-state/upsert`. If this call fails, the pipeline run is retroactively marked as "failed" — even though all operations completed successfully and the data exists in step_results.

This is a design choice (entity state is considered critical), but it means a Supabase hiccup at the very end can negate an entire multi-step enrichment pipeline that may have taken minutes to execute.

### 7.10 No Observability Dashboard

There's no built-in dashboard or monitoring for:
- Pipeline run success/failure rates
- Provider reliability metrics
- Auto-persist success rates
- Entity state coverage gaps
- Fan-out depth/breadth statistics

Debugging requires querying the database directly or reading Trigger.dev logs.

### 7.11 Legacy Dead Code in Trigger.dev

The `trigger/src/tasks/` directory contains several legacy files:
- `execute-step.ts` — Legacy generic step executor, not used by current pipeline runner
- `enrich-apollo.ts` — Legacy Apollo enrichment task
- `deduplicate.ts` — Legacy deduplication task
- `normalize.ts` — Legacy normalization task
- `provider-waterfall-test.ts` — Test task
- `hello-trigger.ts` — Hello world test task

These are not cleaned up and can confuse new contributors.

---

## 8. The Operation Ecosystem

### 8.1 Operation Naming Convention

Operations follow a hierarchical naming: `{entity_type}.{category}.{action}`

```
company.enrich.profile           → Enrich company profile via Prospeo
company.enrich.profile_blitzapi  → Enrich company profile via BlitzAPI
company.search.fmcsa             → Search FMCSA for trucking companies
person.contact.resolve_email     → Find email for a person (provider waterfall)
person.search.sales_nav_url      → Search Sales Navigator for prospects
job.search                       → Search for job postings via TheirStack
```

### 8.2 Provider Ecosystem (20+ providers)

| Provider | Operations | Notes |
|----------|-----------|-------|
| Prospeo | Company enrich, person search | Primary B2B enrichment |
| BlitzAPI | Company/person enrich, LinkedIn resolution | Extensive LinkedIn data |
| Icypeas | Email resolution | Async polling (2s intervals, 45s max) |
| LeadMagic | Email, phone, company enrich | Fallback provider |
| MillionVerifier | Email verification | First-pass verification |
| Reoon | Email verification | Power mode, second-pass |
| Parallel.ai | ICP job titles, intel briefings, domain resolution | Deep research via long-running tasks |
| Gemini | ICP job titles, customer discovery | Google AI for research |
| Adyntel | LinkedIn/Meta/Google ads | Ad intelligence |
| TheirStack | Job search, tech stack, hiring signals | Job posting data |
| Enigma | Company intelligence | GraphQL API |
| Shovels | Construction permits, contractors, markets | Construction industry data |
| StoreLeads | Ecommerce company enrichment | Ecommerce-specific |
| CourtListener | Court filings, bankruptcy | Legal data |
| FMCSA | Trucking company search/enrich | Federal motor carrier data |
| RevenueInfra HQ | Competitors, customers, alumni, champions, SEC filings, CRM resolution | Internal data platform |
| RapidAPI Sales Nav | Alumni search | Sales Navigator scraping |
| AmpleLeads | Phone resolution | Mobile phone fallback |
| OpenAI | Change detection, SEC analysis | LLM analysis |
| Anthropic | (Available but limited use) | LLM analysis |
| Modal | ICP extraction | Serverless Python functions |

### 8.3 HQ Integration (api.revenueinfra.com)

data-engine-x calls HQ for read-only lookups:
- Research: competitors, customers, alumni, champions, VC funding, similar companies, SEC filings
- CRM resolution: 6 `/single` endpoints (domain from email/LinkedIn/name, LinkedIn from domain, person LinkedIn from email, location from domain)
- Job validation: Bright Data cross-source check
- Sales Nav templates: client-specific URL templates

HQ is a separate system. data-engine-x never writes to it.

---

## 9. Deploy Protocol

### The Rule (Non-Negotiable)

```
1. Push to main → Railway auto-deploys (wait 1-2 minutes)
2. ONLY AFTER Railway is live → cd trigger && npx trigger.dev@4.4.0 deploy
```

**Never deploy simultaneously. Never deploy Trigger.dev first.**

### Why

Trigger.dev calls FastAPI internal endpoints. If a new Trigger.dev deploy references a new endpoint that Railway hasn't deployed yet:
- The internal HTTP call returns 404
- Auto-persist try/catch blocks swallow the error
- Pipeline "succeeds" but data doesn't reach dedicated tables
- Requires manual backfill via scripts in `scripts/`

### Environment Vars

| Variable | Where | Purpose |
|----------|-------|---------|
| `DATABASE_URL` | Railway (via Doppler) | Supabase connection |
| `INTERNAL_API_KEY` | Railway + Trigger.dev | Internal service auth |
| `DATA_ENGINE_API_URL` | Trigger.dev | FastAPI callback URL |
| `DATA_ENGINE_INTERNAL_API_KEY` | Trigger.dev | Callback auth |
| `TRIGGER_SECRET_KEY` | Railway | Auth for triggering tasks |
| `TRIGGER_API_URL` | Railway | Trigger.dev API endpoint |
| `PARALLEL_API_KEY` | Trigger.dev only | Parallel.ai (runs directly from Trigger.dev) |
| `SUPER_ADMIN_API_KEY` | Railway | Super-admin auth |
| `REVENUEINFRA_INGEST_API_KEY` | Railway | HQ integration auth |
| Provider API keys | Railway (via Doppler) | Individual provider auth |

---

## 10. Testing

```bash
# Run all tests
doppler run -- pytest

# Or without Doppler
uv run --with pytest --with pytest-asyncio --with pyyaml pytest
```

Tests use mocked Supabase clients and mock provider responses. Key test files:
- `tests/test_batch_flow.py` — Batch submission + pipeline creation
- `tests/test_nested_fan_out.py` — Nested fan-out child run creation
- `tests/test_entity_dedup.py` — Entity deduplication during fan-out
- `tests/test_entity_state.py` — Entity state upsert + identity resolution
- `trigger/src/utils/__tests__/evaluate-condition.test.ts` — Condition evaluation
- `trigger/src/tasks/__tests__/run-pipeline.timeline.test.ts` — Timeline event emission

---

## 11. Known Incidents & Lessons

### ICP Auto-Persist Not Writing (2026-02-25)

**What happened:** 5 companies' ICP job titles succeeded in Trigger.dev but weren't persisted to `icp_job_titles` table.

**Root cause:** Trigger.dev was deployed before Railway was live. The `/api/internal/icp-job-titles/upsert` endpoint returned 404. The try/catch in auto-persist swallowed the error.

**Lesson:** Deploy Railway first, always wait for it to be live before deploying Trigger.dev. The try/catch design is intentional — don't break pipelines for persistence side-effects — but it means silent data loss if the endpoint isn't available.

### Experience Key Dedup Failure (2026-02-25)

**What happened:** 2.17M rows in `core.person_work_history` had stale `experience_key` values from a prior formula. Phase 2 dedup only filled NULL keys, leaving old inconsistent keys. Identical records with different keys weren't detected as duplicates.

**Lesson:** Always recompute ALL values when changing a deduplication formula. Don't assume existing non-NULL values are correct. Treat legacy data as suspect until verified.

---

## 12. Summary of Architectural Risks

| Risk | Severity | Impact |
|------|----------|--------|
| run-pipeline.ts monolith (2,700 lines) | High | Every new operation/table requires modifying this file; hard to review, test, and maintain |
| Auto-persist silent failures | High | Data can be lost without any alert; only discoverable by cross-referencing step_results vs dedicated tables |
| Deploy sequencing dependency | High | Human-dependent process with no automated guard; has already caused production data loss |
| Parallel.ai operations in Trigger.dev | Medium | Breaks the clean boundary; duplicated code; no operation-level audit trail |
| Shallow context merge | Medium | Nested data can be silently overwritten between steps |
| No pipeline-level retry | Medium | Orchestration crashes are not recoverable without manual intervention |
| execute_v1.py giant dispatch | Medium | Adding operations is tedious and error-prone |
| Entity state upsert failure kills run | Medium | All-or-nothing at the end of a successful pipeline |
| No observability | Medium | No dashboards, no alerts on auto-persist failures, no provider reliability tracking |
| Legacy dead code in trigger/ | Low | Confusion for new contributors, no functional impact |
