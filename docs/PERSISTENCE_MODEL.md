# Persistence Model

**Last updated:** 2026-03-18T22:30:00Z

When an operation runs, what data gets saved, where does it go, and under what conditions can data be lost?

---

## Section 1: Persistence Overview

```
Execution entry points:

  POST /api/v1/execute (standalone)
    ──→ operation_runs + operation_attempts        (always, synchronous)
    ──→ HTTP response with full result             (always)
    ──→ entity state upsert                        (NEVER — standalone does not persist to entity tables)
    ──→ dedicated table writes                     (NEVER)
    ──→ timeline events                            (NEVER)

  POST /api/v1/batch/submit (pipeline)
    ──→ submissions row                            (created upfront, status "received" → "queued")
    ──→ pipeline_runs rows (1 per entity)          (created upfront, status "queued")
    ──→ step_results rows (1 per step per run)     (created upfront, status "queued")
    ──→ Trigger.dev task dispatched
      ──→ pipeline_runs status → "running"
      ──→ per step:
          ──→ step_results → "running"
          ──→ POST /api/v1/execute (operation)     → operation_runs + operation_attempts
          ──→ step_results → "succeeded"/"failed"  (output_payload includes operation_result + cumulative_context)
          ──→ timeline event                       (best-effort, failure swallowed)
          ──→ dedicated table auto-persist          (conditional, try/catch, failure swallowed)
      ──→ entity state upsert                      (once at pipeline end, NOT per-step)
      ──→ pipeline_runs status → "succeeded"/"failed"
      ──→ submissions status synced

  FMCSA / Federal bulk ingestion (contrasting pattern)
    ──→ Direct Postgres COPY + temp table merge    (no operation/pipeline path)
    ──→ Trigger.dev task → internal endpoint → raw SQL batch upsert
```

---

## Section 2: Standalone Operation Execution

### Code Path: `POST /api/v1/execute`

**Entry point:** `app/routers/execute_v1.py:269` — `execute_v1()` function.

Every operation follows the same pattern (`execute_v1.py:318-327` as representative example):

```
1. Execute operation → result
2. persist_operation_execution(auth, entity_type, operation_id, input_payload, result)
3. Return DataEnvelope(data=result)
```

### What `persist_operation_execution()` Writes

**File:** `app/services/operation_history.py:18-72`

**`ops.operation_runs`** (line 50):

| Column | Source |
|---|---|
| `run_id` | `result.get("run_id")` — early exit if missing (line 29-30) |
| `org_id` | `auth.org_id` |
| `company_id` | `auth.company_id` |
| `user_id` | `auth.user_id` |
| `role` | `auth.role` |
| `auth_method` | `auth.auth_method` |
| `operation_id` | parameter |
| `entity_type` | parameter |
| `status` | `result.get("status")` or `"failed"` |
| `missing_inputs` | `result.get("missing_inputs")` or `[]` |
| `input_payload` | full input dict |
| `output_payload` | `result.get("output")` — **full output payload stored** |

**`ops.operation_attempts`** (line 71):

| Column | Source |
|---|---|
| `run_id` | FK to operation_runs |
| `provider` | `attempt.get("provider")` or `"unknown"` |
| `action` | `attempt.get("action")` or `"unknown"` |
| `status` | `attempt.get("status")` or `"failed"` |
| `skip_reason` | `attempt.get("skip_reason")` |
| `http_status` | `attempt.get("http_status")` |
| `provider_status` | `attempt.get("provider_status")` |
| `duration_ms` | `attempt.get("duration_ms")` |
| `raw_response` | `attempt.get("raw_response")` — **full provider response stored** |

If `provider_attempts` is empty or missing, attempt logging is skipped (line 53-54).

### Entity State & Dedicated Tables

The standalone execute path does **NOT** trigger:
- Entity state upserts — confirmed by tracing `execute_v1.py`; no call to `upsert_company_entity()` or any entity service
- Dedicated table writes — no auto-persist logic in the execute endpoint
- Timeline events — no timeline recording

### Data Loss Implication

If a client calls `/api/v1/execute` and the HTTP response is lost (network timeout, client crash):

**The result IS recoverable.** Both `persist_operation_execution()` writes (operation_runs and operation_attempts) execute synchronously *before* the HTTP response is returned (line 50, 71 in `operation_history.py`). The full `output_payload` is stored in `operation_runs`. The client can query `operation_runs` by `run_id` or filter by `operation_id` + `org_id` to retrieve the result.

**However:** No entity-level persistence occurs. The data exists only in `operation_runs` as an audit record. To get entity-level persistence (company_entities, person_entities, dedicated tables), the operation must run inside a pipeline.

---

## Section 3: Pipeline Execution Persistence

### 3a: Pipeline Creation (Batch Submit)

**Entry point:** `app/routers/execute_v1.py:1269` — `batch_submit()` → calls `create_batch_submission_and_trigger_pipeline_runs()` at `app/services/submission_flow.py:308`.

**Rows created upfront (synchronously, before Trigger.dev dispatch):**

1. **`ops.submissions`** (submission_flow.py:330-341) — 1 row:
   - `id`, `org_id`, `company_id`, `blueprint_id`, `submitted_by_user_id`, `input_payload` (all entities), `source`, `metadata`, `status` = `"received"` → updated to `"queued"` at line 407

2. **`ops.pipeline_runs`** (submission_flow.py:345-405) — 1 row per entity:
   - `id`, `org_id`, `company_id`, `submission_id`, `blueprint_id`, `blueprint_snapshot` (includes entity sub-object), `blueprint_version` (hash), `status` = `"queued"`, `attempt` = 1, `parent_pipeline_run_id` = null, `trigger_run_id` (populated after Trigger dispatch at line 370-380)
   - Created via `_create_pipeline_run_row()` (line 152-177)

3. **`ops.step_results`** (submission_flow.py:362-368) — 1 row per step per run:
   - `id`, `org_id`, `company_id`, `submission_id`, `pipeline_run_id`, `step_id`, `blueprint_step_id`, `step_position`, `status` = `"queued"`
   - Created via `_create_step_result_rows()` (line 180-212), bulk insert at line 212

### 3b: Pipeline Run Start

**File:** `trigger/src/tasks/run-pipeline.ts`

When Trigger.dev picks up the task:

1. **Load run config** (line 1829): `POST /api/internal/pipeline-runs/get`
2. **Transition to running** (line 1835-1838): `POST /api/internal/pipeline-runs/update-status` with `status: "running"`
3. **Sync submission status** (line 1839): `POST /api/internal/submissions/sync-status`

### 3c: Per-Step Execution

For each step in the pipeline:

#### 1. Step marked running

`run-pipeline.ts:2080-2084`: `POST /api/internal/step-results/update` with `status: "running"` and `input_payload: cumulativeContext`.

#### 2. Operation execution

`run-pipeline.ts:2100`: `POST /api/v1/execute` — this triggers `persist_operation_execution()` on the FastAPI side, writing `operation_runs` + `operation_attempts`.

#### 3. Step result update (succeeded)

`run-pipeline.ts:2483-2494`: `POST /api/internal/step-results/update` with:
```json
{
  "step_result_id": "<id>",
  "status": "succeeded",
  "output_payload": {
    "operation_result": "<full result>",
    "cumulative_context": "<full context snapshot>"
  }
}
```

**The full operation result AND cumulative context are stored in `step_results.output_payload`.** This is significant for recoverability — see Section 5.

#### 4. Step result update (failed)

`run-pipeline.ts:2404-2420`: Same structure with `status: "failed"`, plus `error_message` and `error_details` (operation_id, missing_inputs).

#### 5. Cumulative context merge

`run-pipeline.ts:2400`: After a succeeded step, the output is merged into cumulative context via `mergeContext()` (line 1643-1649):

```typescript
function mergeContext(current, output) {
  if (!output) return current;
  return { ...current, ...output };
}
```

**Shallow merge only.** New keys override old. Nested objects are reference-copied, not deep-merged. Context is **in-memory only** during the run — see Section 5.

#### 6. Entity state upsert

Entity state upsert happens **once at pipeline end** (NOT per-step):

- **Non-fan-out completion** (line 2671-2677): `POST /api/internal/entity-state/upsert` with `pipeline_run_id`, `entity_type`, `cumulative_context`, `last_operation_id`
- **Fan-out completion** (line 2566-2571): Same endpoint, same payload

Entity type is determined once at pipeline start from `run.blueprint_snapshot.entity.entity_type` (line 1851-1856). Defaults to `"company"` if not specified.

The entity type determines which upsert function runs on the FastAPI side:
- `"company"` → `upsert_company_entity()` (`app/services/entity_state.py:574`)
- `"person"` → `upsert_person_entity()` (`app/services/entity_state.py:709`)
- `"job"` → `upsert_job_posting_entity()` (`app/services/entity_state.py:831`)

#### 7. Dedicated table auto-persist

All auto-persist branches live in `run-pipeline.ts:2110-2398`. Every branch follows the same pattern:

```typescript
if (operationId === "<op_id>" && result.status === "found" && result.output) {
  try {
    await internalPost(internalConfig, "/api/internal/<table>/upsert", { ... });
    logger.info("<table> persisted to dedicated table");
  } catch (error) {
    logger.warn("Failed to persist <table> to dedicated table", { error });
    // NO RETHROW — failure swallowed silently
  }
}
```

| Dedicated Table | Triggered By Operation | Output Guard | Internal Endpoint | Lines |
|---|---|---|---|---|
| `icp_job_titles` | `company.derive.icp_job_titles` | `result.output.domain \|\| result.output.company_domain` | `/api/internal/icp-job-titles/upsert` | 2110-2132 |
| `company_intel_briefings` | `company.derive.intel_briefing` | `result.output.domain \|\| result.output.target_company_domain` | `/api/internal/company-intel-briefings/upsert` | 2134-2159 |
| `person_intel_briefings` | `person.derive.intel_briefing` | `result.output.full_name \|\| result.output.person_full_name` | `/api/internal/person-intel-briefings/upsert` | 2161-2190 |
| `company_customers` | `company.research.discover_customers_gemini` OR `company.research.lookup_customers_resolved` | `Array.isArray(customers) && customers.length > 0` AND `companyDomain` | `/api/internal/company-customers/upsert` | 2192-2227 |
| `gemini_icp_job_titles` | `company.research.icp_job_titles_gemini` | `companyDomain` derived from output or context | `/api/internal/gemini-icp-job-titles/upsert` | 2229-2262 |
| `company_ads` (LinkedIn) | `company.ads.search.linkedin` | `Array.isArray(ads) && ads.length > 0` AND `companyDomain` | `/api/internal/company-ads/upsert` | 2264-2295 |
| `company_ads` (Meta) | `company.ads.search.meta` | `Array.isArray(ads = output.results) && ads.length > 0` AND `companyDomain` | `/api/internal/company-ads/upsert` | 2297-2328 |
| `company_ads` (Google) | `company.ads.search.google` | `Array.isArray(ads) && ads.length > 0` AND `companyDomain` | `/api/internal/company-ads/upsert` | 2330-2361 |
| `salesnav_prospects` | `person.search.sales_nav_url` | `Array.isArray(results) && results.length > 0` AND `sourceCompanyDomain` | `/api/internal/salesnav-prospects/upsert` | 2363-2398 |

**All 9 branches use try/catch with swallowed failures.** Pipeline continues and succeeds even if the dedicated table write fails.

#### 8. Timeline event recording

Timeline events are emitted via `emitStepTimelineEvent()` (`run-pipeline.ts:1747-1801`), which calls `POST /api/internal/entity-timeline/record-step-event`.

**When emitted:**
- After step succeeds (line 2495-2509)
- After step fails (line 2421-2440)
- When step is skipped — condition false (line 1960-1974), entity fresh (line 2052-2067), upstream failed (line 1915-1928, 2451-2469), parent condition fails (line 1998-2016)
- When operation execution throws (line 2607-2621)

**Failure handling:** Timeline emit failures are caught and logged as warnings (`run-pipeline.ts:1790-1799`). They do NOT propagate to pipeline status.

On the FastAPI side, `record_entity_event()` (`app/services/entity_timeline.py:34-99`) is explicitly best-effort — docstring states "Never raises to callers" (line 50). All exceptions caught and logged; returns None on failure.

#### 9. Entity relationship recording

Entity relationships are **NOT** recorded by `run-pipeline.ts`. The 1,892 rows in `entity_relationships` are all from Clay ingestion (external ingest path), not pipeline execution.

Relationships are recorded via:
- `POST /api/internal/entity-relationships/record` (`app/routers/internal.py:591`)
- `POST /api/internal/entity-relationships/record-batch` (`app/routers/internal.py:615`)
- Called by fan-out in `app/routers/internal.py:1280,1311` (records fan-out discovery events as entity relationships)

### 3d: Pipeline Completion

**All steps succeed (non-fan-out):**
1. Entity state upsert (line 2671-2677)
2. Pipeline run → `"succeeded"` (line 2665-2669)
3. Submission status synced (line 2691)

**All steps succeed (fan-out):**
1. Fan-out child runs created via `POST /api/internal/pipeline-runs/fan-out` (line 2524)
2. Fan-out step result updated with child_run_ids (line 2542-2557)
3. Entity state upsert for parent (line 2566-2571)
4. Parent pipeline run → `"succeeded"` (line 2559-2563)
5. Submission status synced (line 2585)
6. Each child run executes independently as a full pipeline

**Step fails:**
1. Step result → `"failed"` with error details (line 2404-2420)
2. Timeline event emitted (line 2421-2440)
3. Remaining steps marked skipped via `POST /api/internal/step-results/mark-remaining-skipped` (line 2441-2448)
4. Pipeline run → `"failed"` (line 2471-2475)
5. Submission status synced (line 2477)
6. **Entity state upsert does NOT happen on failure** — only on success

**Entity upsert itself fails:**
1. Pipeline run → `"failed"` with error message (line 2680-2684)
2. Submission status synced (line 2691)

---

## Section 4: Confirmed Writes vs Auto-Persist

| Aspect | Auto-Persist (run-pipeline.ts) | Confirmed Writes (dedicated workflows) |
|---|---|---|
| Error handling | `try/catch`, warn log, execution continues | Throws `PersistenceConfirmationError`, execution stops |
| Failure visibility | Silent — pipeline succeeds even if persist fails | Loud — pipeline fails if persist fails |
| Where defined | Inline in `run-pipeline.ts` per operation ID (lines 2110-2398) | `trigger/src/workflows/persistence.ts` shared module |
| Used by | Legacy generic pipeline runner | Dedicated workflow files |
| Production evidence | `company_customers` (0 rows / 18 successful steps), `gemini_icp_job_titles` (0 rows / 20 steps), `salesnav_prospects` (0 rows / 35 steps) | `icp_job_titles` (156 rows healthy), `company_intel_briefings` (3 rows healthy), `person_intel_briefings` (1 row healthy) |

### Confirmed Writes Implementation

**File:** `trigger/src/workflows/persistence.ts`

Three key functions:

1. **`confirmedInternalWrite()`** (line 47-66): Calls `client.post()`, validates response with optional validator, throws `PersistenceConfirmationError` on failure.

2. **`upsertEntityStateConfirmed()`** (line 68-84): Wraps `confirmedInternalWrite()` for `/api/internal/entity-state/upsert`. Validates response has `entity_id`.

3. **`writeDedicatedTableConfirmed()`** (line 86-91): Generic wrapper for any dedicated table write.

**Error class:** `PersistenceConfirmationError` (line 5-15) with `path` and `responseData` properties.

### InternalApiClient Error Behavior

**File:** `trigger/src/workflows/internal-api.ts`

The `InternalApiClient.post()` method (line 131-208):
- Gzip-compresses payload (line 142)
- Throws `InternalApiTimeoutError` on timeout (line 158-171)
- Throws `InternalApiError` on non-2xx HTTP status (line 176-185)
- Throws `InternalApiError` on missing/invalid response envelope (line 187-194)
- **No retry logic** — fail-fast design
- **All errors surfaced** — nothing swallowed

### Dedicated Workflows Using Confirmed Writes

Example: ICP Job Titles Discovery (`trigger/src/workflows/icp-job-titles-discovery.ts`):

- Entity state upsert (line 399-415): calls `upsertEntityStateConfirmed()`, catches error into outcome tracker
- Dedicated table write (line 418-440): calls `writeIcpJobTitlesConfirmed()`, catches error into outcome tracker
- Persistence result check (line 641-663): after both writes, checks if either failed → marks pipeline run as failed

**Key difference from auto-persist:** Dedicated workflows catch persistence errors and track them in an outcome object, then set pipeline status based on aggregated results. The pipeline *fails* if persistence fails — it does not silently succeed.

### Operation IDs Still on Auto-Persist

These operations are called from `run-pipeline.ts` and use the fragile try/catch pattern:
- `company.derive.icp_job_titles`
- `company.derive.intel_briefing`
- `person.derive.intel_briefing`
- `company.research.discover_customers_gemini`
- `company.research.lookup_customers_resolved`
- `company.research.icp_job_titles_gemini`
- `company.ads.search.linkedin`
- `company.ads.search.meta`
- `company.ads.search.google`
- `person.search.sales_nav_url`

Some of these (icp_job_titles, company/person intel briefings) also have dedicated workflow paths with confirmed writes, making them "Mixed" reliability. Others (company_customers, gemini_icp_job_titles, salesnav_prospects, company_ads) are auto-persist only and "Fragile."

---

## Section 5: Cumulative Context

### What It Is

The accumulated state of the pipeline entity, growing with each step's output. It represents the canonical payload for the entity being enriched.

### Where It Lives

**In-memory only**, declared at `run-pipeline.ts:1864`:

```typescript
let cumulativeContext: Record<string, unknown> = { ...initialInput };
```

`initialInput` comes from `snapshotEntity.input` (fan-out) or `submissionInput` (root run).

### How It's Built

1. **Initialized** from entity input (line 1857-1864)
2. **Merged after each succeeded step** via `mergeContext()` (line 2400)
3. **Merged from freshness check** if entity is fresh (line 2037) — canonical payload from existing entity state is merged back into context

`mergeContext()` (line 1643-1649) does a **shallow spread**: `{ ...current, ...output }`. Output keys override current keys. Nested objects are not deep-merged.

### Durability

**Cumulative context is NOT durable.** It exists only in the Trigger.dev task's runtime memory. If the task crashes, the variable is lost.

**However:** Each succeeded step's `step_results.output_payload` stores `{ operation_result, cumulative_context }` (line 2483-2494). This means the cumulative context *at each step completion* is persisted as a snapshot inside step_results. It could theoretically be reconstructed by reading the last succeeded step's output_payload.

### Freshness Checking

**Skip-if-fresh** logic (`run-pipeline.ts:2024-2078`):

1. Step must have `skip_if_fresh` config with `max_age_hours` and `identity_fields` (extracted via `getSkipIfFreshConfig()`, line 1694-1713)
2. Identity fields extracted from cumulative context (line 2032)
3. Calls `POST /api/internal/entity-state/check-freshness` (line 2028)
4. **If fresh:** Merges `canonical_payload` from existing entity into context (line 2037), marks step as skipped with reason `"entity_state_fresh"` (line 2049)
5. **If not fresh:** Continues with live execution
6. **If check fails:** Catches error, logs warning, continues with live execution (line 2070-2077)

**FastAPI side:** `app/routers/internal.py:574` — checks entity table by natural key identifiers, returns `fresh` boolean, `age_hours`, and `canonical_payload`.

### Entity State Upsert as Checkpoint

When entity state is upserted at pipeline end (line 2671-2677), the `cumulative_context` is passed to `upsert_company_entity()` / `upsert_person_entity()` / `upsert_job_posting_entity()`. These functions extract canonical fields from the context and persist them as the entity's `canonical_payload`.

This is a **de facto checkpoint**: the entity's canonical state in the database reflects the accumulated context at pipeline completion. However, it only happens once at the end — there are no mid-pipeline entity state checkpoints.

### What Happens on Mid-Pipeline Failure

If the pipeline fails at step N:
- **Recoverable:** Steps 1 through N-1 have their `output_payload` (including cumulative_context snapshots) stored in `step_results`. Individual `operation_runs` store each step's raw output.
- **Lost:** The cumulative_context variable (only in memory). However, the last succeeded step's `step_results.output_payload.cumulative_context` contains the context up to that point.
- **NOT persisted:** Entity state upsert does not happen on failure. The entity's canonical payload in `company_entities`/`person_entities` is not updated with data from earlier successful steps.

---

## Section 6: Array and Multi-Entity Results

### Current Handling

Entity state upsert functions (`upsert_company_entity()`, `upsert_person_entity()`, `upsert_job_posting_entity()`) handle **single entities only**. They do not iterate over arrays. If an operation returns an array of 50 companies, the entity upsert receives the cumulative context (which contains the array as a single key) and extracts fields for one entity — typically the first match or the entity described by top-level fields.

### Fan-Out as the Solution

Fan-out creates child pipeline runs for each entity in an array result:

1. Parent step produces array result with `results` key
2. `extractFanOutResults()` (`run-pipeline.ts:1651-1656`) extracts the `results` array
3. `POST /api/internal/pipeline-runs/fan-out` creates one child pipeline run per array item
4. Each child executes from the next step position with its own entity input
5. Each child goes through the standard single-entity persistence path

### Non-Fan-Out Array Results

If an operation returns an array and there's no fan-out configured:
- The array is stored in `step_results.output_payload.operation_result` — data is preserved
- The array is merged into cumulative context as a single key
- Entity state upsert at pipeline end extracts fields from the context — **it does not iterate**
- Individual entities from the array are NOT created as separate entity rows
- **The array data is preserved in step_results but not materialized into entity tables**

### Dedicated Table Array Handling

Several dedicated table services handle arrays natively:

| Service | Array Support |
|---|---|
| `upsert_company_customers()` | YES — accepts `customers: list[dict]`, iterates per customer, bulk upsert |
| `upsert_company_ads()` | YES — accepts `ads: list[dict]`, splits on `ad_id` presence for dual upsert/insert |
| `upsert_salesnav_prospects()` | YES — accepts `prospects: list[dict]`, iterates per prospect, bulk upsert |
| `upsert_icp_job_titles()` | NO — single-row upsert, stores `raw_parallel_output` as monolithic JSONB |
| `upsert_company_intel_briefing()` | NO — single-row upsert |
| `upsert_person_intel_briefing()` | NO — single-row upsert |
| `upsert_gemini_icp_job_titles()` | YES (fields) — stores `titles`, `champion_titles`, etc. as JSONB arrays within a single row |
| `record_entity_relationships_batch()` | YES — batch wrapper, calls per-item with error swallowing |

---

## Section 7: Fan-Out Persistence

### How Fan-Out Works

1. Parent pipeline run executes steps up to the fan-out step
2. Fan-out step produces an array result (e.g., a search returning 20 companies)
3. `extractFanOutResults()` (line 1651-1656) extracts the `results` array from output
4. `POST /api/internal/pipeline-runs/fan-out` (line 2524) creates child pipeline runs
5. Each child receives its own entity input and starts execution from `start_from_position` (fan-out step position + 1)

### What's Persisted for the Parent

- **Step result** (line 2542-2557): The fan-out step's `output_payload` includes:
  - `operation_result`: full operation output
  - `cumulative_context`: context at fan-out point
  - `fan_out`: `{ child_run_ids, child_count, child_count_created, child_count_skipped_duplicates, skipped_duplicate_identifiers, start_from_position }`
- **Entity state upsert** (line 2566-2571): Parent entity gets upserted with cumulative context at fan-out point
- **Pipeline run status** → `"succeeded"` (line 2559-2563)

### What's Persisted for Each Child

Each child is an independent pipeline run with:
- Its own `pipeline_runs` row (with `parent_pipeline_run_id` set)
- Its own `step_results` rows (starting from `start_from_position`)
- Its own entity state upsert at completion
- Its own dedicated table auto-persist branches
- Its own timeline events

### Fan-Out Router

The fan-out router task (`trigger/src/tasks/`) dispatches child runs to the appropriate execution path:
- **Dedicated workflows**: if a dedicated workflow exists for the pipeline type, the router triggers it
- **Generic run-pipeline**: fallback for unmigrated pipelines

### Entity Relationships from Fan-Out

Fan-out creation in `app/routers/internal.py` (lines 1280, 1311) records entity relationships. For example, fan-out from a company to discovered persons creates `person → works_at → company` relationships via the entity-relationships/record endpoint.

---

## Section 8: Data Loss Risk Inventory

### Risk 1: Standalone Execute — Audit-Only Persistence

- **Risk:** Standalone `/api/v1/execute` results are stored in `operation_runs` but no entity upsert occurs
- **Trigger:** Any standalone operation call
- **Impact:** Data exists only as an audit record. Not materialized into entity tables or dedicated tables. Not available to freshness checks or entity queries.
- **Evidence:** By design — confirmed by tracing `execute_v1.py` (no entity upsert calls)
- **Mitigation:** Use pipeline execution (batch submit) for entity-level persistence. `operation_runs.output_payload` contains the full result for manual recovery.

### Risk 2: Silent Auto-Persist Failure

- **Risk:** The try/catch pattern in `run-pipeline.ts:2110-2398` swallows dedicated table write failures. Pipeline reports success; data never reaches the dedicated table.
- **Trigger:** Internal endpoint returns error (HTTP 4xx/5xx), timeout, invalid payload shape, or deploy-timing mismatch (endpoint doesn't exist yet)
- **Impact:** Dedicated table has zero rows despite successful operation steps
- **Evidence:**
  - `company_customers`: 0 rows despite 18 successful steps (OPERATIONAL_REALITY_CHECK)
  - `gemini_icp_job_titles`: 0 rows despite 20 successful steps
  - `salesnav_prospects`: 0 rows despite 35 successful steps
  - `company_ads`: 0 rows
- **Mitigation:** Migrate to confirmed writes (dedicated workflow pattern). Data is still in `step_results.output_payload` and can be backfilled.

### Risk 3: Context Shape Failure

- **Risk:** Auto-persist branches guard on specific output field names. If the operation produces a valid result but the field names don't match the guard, the branch doesn't fire.
- **Trigger:** Operation output shape evolves without updating auto-persist guards, or upstream context doesn't carry required fields
- **Impact:** Dedicated table write never attempted — no error logged, no warning, complete silence
- **Evidence:** `salesnav_prospects` — successful `person.search.sales_nav_url` steps don't carry `sourceCompanyDomain` in the context, so the guard at line 2363-2375 never fires
- **Mitigation:** Confirmed writes in dedicated workflows extract fields explicitly from operation output, not from context shape assumptions.

### Risk 4: Deploy-Timing Landmine

- **Risk:** Railway must deploy before Trigger.dev. If Trigger deploys first, new internal endpoint calls hit 404s.
- **Trigger:** Trigger.dev deployment includes calls to internal endpoints that don't exist on the currently-running Railway instance
- **Impact:** Pipeline continues (internal post returns 404, caught by try/catch in auto-persist → swallowed). Entity state upsert calls to new endpoints fail loudly (not in try/catch).
- **Evidence:** Documented in `DATA_ENGINE_X_ARCHITECTURE.md` Section 7
- **Mitigation:** Deploy Railway first, wait for health check, then deploy Trigger.dev. Exception: fan-out router deploys require Trigger first.

### Risk 5: Cumulative Context Loss on Crash

- **Risk:** If a Trigger task crashes mid-pipeline, the in-memory cumulative context variable is lost
- **Trigger:** Trigger.dev task crash, OOM, timeout, infrastructure failure
- **Impact:** Entity state upsert never happens (only runs at pipeline end). Cumulative context is lost. Earlier successful steps' data is NOT reflected in entity tables.
- **Evidence:** No direct production evidence in operational reality check, but the architectural risk is structural
- **Mitigation:** Step results store `cumulative_context` snapshots in `output_payload`. Reconstruction is possible by reading the last succeeded step's output. No automated recovery mechanism exists.

### Risk 6: Entity Upsert Natural Key Race

- **Risk:** Two concurrent pipeline runs for the same entity (e.g., same company domain) race on the entity upsert
- **Trigger:** Parallel pipeline runs processing the same entity
- **Impact:** Optimistic concurrency — `upsert_company_entity()` uses `record_version` (line 607-612 in entity_state.py). If versions don't match, raises `EntityStateVersionError` (line 702). The pipeline fails.
- **Evidence:** No direct production evidence
- **Mitigation:** Optimistic locking prevents silent data corruption — the second write fails loudly. However, the failing pipeline's enrichment data is lost (no retry).

### Risk 7: Timeline Event Loss

- **Risk:** Timeline events use best-effort writes. `record_entity_event()` never raises (entity_timeline.py:50). `emitStepTimelineEvent()` catches and warns (run-pipeline.ts:1790-1799).
- **Trigger:** Any failure in timeline write (DB error, timeout, etc.)
- **Impact:** Timeline history is incomplete — events are silently dropped
- **Evidence:** No direct production evidence of dropped events
- **Mitigation:** None. Timeline is explicitly designed as best-effort.

### Risk 8: Entity State Upsert Failure at Pipeline End

- **Risk:** Entity state upsert happens once at pipeline end. If it fails, the pipeline is marked failed despite all operation steps succeeding.
- **Trigger:** DB error, version conflict, invalid context shape
- **Impact:** Entity canonical state not updated. All step results are persisted, but the entity table doesn't reflect the enrichment.
- **Evidence:** Handled at `run-pipeline.ts:2680-2684` — pipeline transitions to `"failed"`
- **Mitigation:** Step results contain full data. Manual recovery possible. No automatic retry.

### Risk 9: FMCSA Bulk Write Partial Failure

- **Risk:** FMCSA bulk writes use Postgres COPY + temp table merge (`app/services/fmcsa_daily_diff_common.py:375-549`). A failure mid-transaction rolls back the entire batch.
- **Trigger:** Statement timeout (600s limit at line 485), constraint violation, connection loss
- **Impact:** Entire batch of rows (potentially tens of thousands) lost. Must re-run the feed ingestion task.
- **Evidence:** FMCSA tables are healthy (75.8M rows), suggesting this is rare but architecturally possible
- **Mitigation:** Transaction rollback is atomic — no partial corruption. Re-running the feed task retries the entire batch.

---

## Section 9: Persistence Decision Tree

```
My operation returns a result. How do I make sure it persists?

1. Is this operation called standalone (POST /api/v1/execute only)?
   → Result stored in ops.operation_runs.output_payload
     (app/services/operation_history.py:50)
   → BUT: no entity upsert, no dedicated table write, no timeline event
   → Data is audit-only — not queryable via entity endpoints
   → If you need entity-level persistence → run inside a pipeline

2. Is this operation part of a pipeline?

   2a. Does it produce a single-entity result?
       → Step result stored in ops.step_results.output_payload
         (run-pipeline.ts:2483-2494)
       → Result merged into cumulative context
         (run-pipeline.ts:2400, via mergeContext at line 1643)
       → Entity state upserted at pipeline end (NOT per-step)
         (run-pipeline.ts:2671-2677 → app/services/entity_state.py)
       → Entity type determined by blueprint_snapshot.entity.entity_type

   2b. Does it produce a multi-entity result (array)?
       → WITHOUT fan-out: array stored in step_results, but individual
         entities are NOT created in entity tables
       → WITH fan-out: each array item becomes a child pipeline run
         (run-pipeline.ts:2512-2540 → /api/internal/pipeline-runs/fan-out)
       → Each child goes through standard single-entity persistence

   2c. Does it produce data for a dedicated table?
       → Option A (LEGACY — NOT recommended):
         Add auto-persist branch in run-pipeline.ts:2110-2398
         ⚠ Uses try/catch that swallows failures
         ⚠ Production evidence of zero-row tables from this pattern
       → Option B (RECOMMENDED):
         Create dedicated workflow file using confirmed writes from
         trigger/src/workflows/persistence.ts
         - writeDedicatedTableConfirmed() (line 86-91) for dedicated tables
         - upsertEntityStateConfirmed() (line 68-84) for entity state
         - Both throw PersistenceConfirmationError on failure

3. Is this a bulk ingestion operation (like FMCSA)?
   → Use direct batch upsert pattern
     (see app/services/fmcsa_daily_diff_common.py:375-549)
   → Write a service function with Postgres COPY + temp table merge
   → Wire to an internal endpoint in app/routers/internal.py
   → Call from Trigger.dev ingestion task
   → Transaction: all-or-nothing per batch
```

---

## Section 10: Table-Level Persistence Reference

### Orchestration Tables (ops schema)

| Table | Written By | Execution Path | Reliability | Notes |
|---|---|---|---|---|
| `ops.submissions` | `create_batch_submission_and_trigger_pipeline_runs()` | Pipeline only | Reliable | Created upfront; status synced after each run status change |
| `ops.pipeline_runs` | `_create_pipeline_run_row()` + internal update-status | Pipeline only | Reliable | Created upfront; status transitions via internal endpoint |
| `ops.step_results` | `_create_step_result_rows()` + internal update | Pipeline only | Reliable | Created upfront; updated per-step with full output_payload |
| `ops.operation_runs` | `persist_operation_execution()` | Both standalone + pipeline | Reliable | Full input/output payload stored |
| `ops.operation_attempts` | `persist_operation_execution()` | Both standalone + pipeline | Reliable | Per-provider attempt with raw_response |

### Entity Tables (entities schema)

| Table | Written By | Execution Path | Reliability | Natural Key | Production Rows |
|---|---|---|---|---|---|
| `entities.company_entities` | `upsert_company_entity()` via internal endpoint | Pipeline (end) | Reliable | `canonical_domain` or `company_linkedin_url` | 45,679 |
| `entities.person_entities` | `upsert_person_entity()` via internal endpoint | Pipeline (end) | Reliable | `linkedin_url` or `work_email` | 2,116 |
| `entities.job_posting_entities` | `upsert_job_posting_entity()` via internal endpoint | Pipeline (end) | Reliable | `theirstack_job_id` | 1 |
| `entities.entity_timeline` | `record_entity_event()` via internal endpoint | Pipeline (per-step, best-effort) | Best-effort | N/A (append-only) | 4,345 |
| `entities.entity_snapshots` | `_capture_entity_snapshot()` in entity_state.py | Pipeline (entity upsert) | Best-effort | N/A (append-only) | 6,407 |
| `entities.entity_relationships` | `record_entity_relationship()` via internal endpoint | Clay ingestion + fan-out | Reliable | `(org_id, source_identifier, relationship, target_identifier)` | 1,892 |
| `entities.company_entity_associations` | `record_company_entity_association()` in internal.py | Pipeline (entity upsert) | Reliable | `(org_id, company_id, entity_id)` | — |

### Dedicated Tables (entities schema)

| Table | Written By | Execution Path | Reliability | Upsert Key | Production Rows |
|---|---|---|---|---|---|
| `entities.icp_job_titles` | Auto-persist + confirmed write | Pipeline (conditional) | Mixed | `(org_id, company_domain)` | 156 (healthy) |
| `entities.company_intel_briefings` | Auto-persist + confirmed write | Pipeline (conditional) | Mixed | `(org_id, company_domain, client_company_name)` | 3 (healthy) |
| `entities.person_intel_briefings` | Auto-persist + confirmed write | Pipeline (conditional) | Mixed | `(org_id, person_full_name, person_current_company_name, client_company_name)` | 1 (healthy) |
| `entities.company_customers` | Auto-persist only | Pipeline (conditional) | **Fragile** | `(org_id, company_domain, customer_domain)` | **0** (broken) |
| `entities.gemini_icp_job_titles` | Auto-persist only | Pipeline (conditional) | **Fragile** | `(org_id, company_domain)` | **0** (broken) |
| `entities.company_ads` | Auto-persist only | Pipeline (conditional) | **Fragile** | `(org_id, company_domain, platform, ad_id)` | **0** (broken) |
| `entities.salesnav_prospects` | Auto-persist only | Pipeline (conditional) | **Fragile** | `(org_id, source_company_domain, linkedin_url)` | **0** (broken) |
| `entities.extracted_icp_job_title_details` | Unknown | Unknown | N/A | — | **0** (never used) |

### FMCSA Tables (entities schema) — Contrasting Pattern

18 canonical tables written by direct Postgres COPY + temp table merge via `upsert_fmcsa_daily_diff_rows()` (`app/services/fmcsa_daily_diff_common.py:375-549`). ~75.8M total rows. Daily feed ingestion active. Does NOT use the operation/pipeline execution path.

### Federal Data Tables (entities schema)

| Table | Written By | Execution Path | Reliability | Production Rows |
|---|---|---|---|---|
| `entities.sam_gov_entities` | `sam_gov_ingest` internal endpoint | Trigger.dev ingestion task | Reliable | 867,137 |
| `entities.sba_7a_loans` | `sba-7a-loans/ingest` internal endpoint | Trigger.dev ingestion task | Reliable | 356,375 |
| `entities.usaspending_contracts` | `usaspending-contracts/ingest` internal endpoint | Trigger.dev ingestion task | Reliable | 14,665,610 |
| `entities.mv_federal_contract_leads` | Materialized view | Refresh script | Reliable | 1,340,862 |
