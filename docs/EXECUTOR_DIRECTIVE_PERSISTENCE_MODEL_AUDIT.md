# Executor Directive: Persistence Model Audit & Reference

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** There is no single document that answers: "when an operation runs, what data gets saved, where does it go, and under what conditions can data be lost?" The persistence model spans multiple systems (FastAPI services, Trigger.dev tasks, internal HTTP callbacks), uses two fundamentally different reliability patterns (silent auto-persist vs confirmed writes), and has known production breakage where successful operations produce zero persisted rows. Engineers building new operations or debugging data loss currently must trace code across 15+ files. This guide consolidates that into one reference.

---

## Existing code to read

Before writing anything, the executor must trace the actual code for every claim. Do not infer from docs or architecture summaries. Every claim must reference specific files and line numbers.

### Primary execution entry points

- `app/routers/execute_v1.py` — the `/api/v1/execute` endpoint and `/api/v1/batch/submit`. Trace what happens to the operation result after it returns. Find `persist_operation_execution()` and understand what it writes. Also trace the batch submit flow to understand how submissions and pipeline runs are created.

### Operation execution audit

- `app/services/operation_history.py` — `persist_operation_execution()`. Trace exactly what goes into `operation_runs` (the run-level record) and `operation_attempts` (the per-provider attempt records). Document whether the full result payload is stored or just metadata. Document the full column list written to each table.

### Pipeline execution persistence (legacy)

- `trigger/src/tasks/run-pipeline.ts` — the legacy generic pipeline runner. This is the most complex file. Trace these specific paths:
  - **Cumulative context**: where it's initialized (from entity input), how it's merged after each step (`mergeContext()`), whether it's stored anywhere durable during the run, and what happens to it if the pipeline fails mid-run.
  - **Step result updates**: when and how `step_results` rows are updated (status, output payload, timing). Find the internal API calls that update step results.
  - **Entity state upsert**: when and how entity tables (`company_entities`, `person_entities`) are updated during pipeline execution. What triggers this — is it every step, only final steps, only specific operations? What determines company vs person vs job posting?
  - **Auto-persist to dedicated tables**: find every auto-persist branch (lines ~2110-2398). For each: what operation ID triggers it, what output shape guard exists, what internal endpoint is called, and critically — the try/catch pattern that swallows failures. Document every dedicated table that has an auto-persist branch.
  - **Pipeline run status updates**: when the run status transitions (queued → running → succeeded → failed), what writes occur.

### Pipeline execution persistence (dedicated workflows)

- `trigger/src/workflows/persistence.ts` — the confirmed-writes module. Trace `confirmedInternalWrite()`, `upsertEntityStateConfirmed()`, `writeDedicatedTableConfirmed()`. Document how these differ from the auto-persist try/catch pattern — specifically that they throw on failure instead of swallowing it.
- At least 2-3 dedicated workflow files in `trigger/src/tasks/` (e.g., the ICP job titles workflow, company intel briefing workflow, person search/enrichment workflow) — trace how they call the confirmed-write functions. Compare their persistence path to run-pipeline.ts to illustrate the difference concretely.

### Entity state upsert logic

- `app/services/entity_state.py` — the canonical entity upsert functions: `upsert_company_entity()`, `upsert_person_entity()`, `upsert_job_posting_entity()`. Trace:
  - Natural key resolution: how does the system decide whether to create a new entity or update an existing one? What natural keys are used for each entity type? (company: `canonical_domain` or `company_linkedin_url`; person: `linkedin_url` or `work_email`; job: `theirstack_job_id`)
  - Field extraction: how are canonical fields extracted from cumulative context?
  - Snapshot capture: does the upsert also create a snapshot?
  - Timeline recording: does the upsert also record a timeline event?
  - Association: does the upsert also create company_entity_associations?

### Entity timeline and snapshots

- `app/services/entity_timeline.py` — timeline event recording. When are events created and what triggers them?
- Find the entity snapshot logic — where snapshots are captured (likely in entity_state.py or a dedicated service). What triggers a snapshot?

### Internal persistence endpoints

- `app/routers/internal.py` — all `/api/internal/*` POST endpoints. List every endpoint, what table it writes to, what auth it requires, and what validation it performs. Group them:
  - Pipeline orchestration endpoints (pipeline-runs/update-status, step-results/update, etc.)
  - Entity endpoints (entity-state/upsert, entity-timeline/record-step-event, etc.)
  - Dedicated table endpoints (icp-job-titles/upsert, company-intel-briefings/upsert, etc.)
  - FMCSA feed endpoints (if applicable — briefly note these exist but they're a different pattern)

### Dedicated table upsert services

- `app/services/icp_job_titles.py` — `upsert_icp_job_titles()`
- `app/services/company_intel_briefings.py` — `upsert_company_intel_briefing()`
- `app/services/person_intel_briefings.py` — `upsert_person_intel_briefing()`
- `app/services/company_customers.py` — `upsert_company_customers()`
- `app/services/gemini_icp_job_titles.py` — `upsert_gemini_icp_job_titles()`
- `app/services/company_ads.py` — `upsert_company_ads()`
- `app/services/salesnav_prospects.py` — `upsert_salesnav_prospects()`
- `app/services/entity_relationships.py` — `record_entity_relationship()`, `record_entity_relationships_batch()`

For each: what columns are written, what's the upsert key, what validation exists, and is the full result payload stored or a subset?

### Trigger.dev internal API client

- `trigger/src/workflows/internal-api.ts` — the `InternalApiClient` class. Trace how it makes HTTP calls to FastAPI. What happens on HTTP error? Does it retry? Does it surface the error or swallow it? This is critical because every persistence call from Trigger goes through this client.

### FMCSA bulk write path (contrasting pattern)

- `app/services/fmcsa_daily_diff_common.py` — the FMCSA bulk write pattern. Briefly document this as a contrasting persistence model: direct batch upserts to the database, not going through the operation/pipeline execution path. This is included to show that not all data persistence follows the operation → pipeline → auto-persist pattern.

### Cross-reference for production state

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` (or `2026-03-10` if 2026-03-18 doesn't exist yet) — the broken tables section. Cross-reference which dedicated tables have zero rows despite successful upstream operations. This is evidence of persistence failures.
- `docs/DATA_ENGINE_X_ARCHITECTURE.md`, section 7 "Known Architectural Problems" — the auto-persist silent failures documented there.

---

## Deliverable 1: Persistence Model Reference

Create `docs/PERSISTENCE_MODEL.md`.

Add a last-updated timestamp at the top:

```markdown
# Persistence Model

**Last updated:** 2026-03-18T[HH:MM:SS]Z

When an operation runs, what data gets saved, where does it go, and under what conditions can data be lost?
```

### Required sections

---

#### Section 1: Persistence Overview

A concise map of the persistence landscape. Present as a layered diagram in text/table form showing:

```
Execution entry points:
  POST /api/v1/execute (standalone)  ──→  operation_runs + operation_attempts (always)
                                          entity state upsert (never — standalone only returns, does not persist to entity tables)

  POST /api/v1/batch/submit (pipeline) ──→ submission + pipeline_runs + step_results (created upfront)
                                            ──→ Trigger.dev task dispatched
                                              ──→ per step: operation_runs + operation_attempts
                                              ──→ per step: step_results updated
                                              ──→ entity state upsert (conditional)
                                              ──→ dedicated table auto-persist (conditional, fragile)
                                              ──→ timeline events (conditional)
```

This should give a reader the entire picture in 30 seconds. The details follow in subsequent sections.

---

#### Section 2: Standalone Operation Execution

Trace the exact code path for `POST /api/v1/execute`:

1. What happens to the operation result? Is it only returned in the HTTP response?
2. Does `persist_operation_execution()` run? What does it write to `operation_runs` and `operation_attempts`?
3. Does the standalone execute path trigger entity state upserts? (Expected answer: no — but trace the code to confirm.)
4. Does the standalone execute path trigger dedicated table writes? (Expected answer: no — but trace the code to confirm.)
5. **Data loss implication:** If a client calls `/api/v1/execute` and the response is lost (network timeout, client crash), is the result recoverable from any database table? Document the answer clearly.

Include code references (file:line) for every claim.

---

#### Section 3: Pipeline Execution Persistence

Trace the full pipeline execution persistence path, step by step. For each stage of the pipeline lifecycle, document exactly what gets written and when.

##### 3a: Pipeline Creation (batch submit)

What rows are created when a batch is submitted? Document the upfront creation of submission, pipeline_runs, and step_results rows with their initial statuses.

##### 3b: Pipeline Run Start

When Trigger.dev picks up the task, what status updates occur? Where in run-pipeline.ts does the run transition from `queued` to `running`?

##### 3c: Per-Step Execution

For each step in the pipeline:

1. **Operation execution**: the step calls `/api/v1/execute` (or the internal equivalent). What gets persisted at this point? (Answer: `operation_runs` + `operation_attempts` via `persist_operation_execution()`)
2. **Step result update**: after the operation returns, run-pipeline.ts calls the internal step-results/update endpoint. Document what's sent: status, output payload, timing, error info. Is the full operation output stored in the step result, or just metadata?
3. **Cumulative context merge**: the step output is merged into cumulative context. Document the merge strategy (shallow merge, new keys override old). Document that cumulative context is **in-memory only** — not persisted to any durable store during the run.
4. **Entity state upsert**: document when this happens. Is it after every step? Only after specific steps? Only at pipeline completion? Trace the code to find the exact trigger. Document what determines whether a `company_entities` vs `person_entities` vs `job_posting_entities` upsert occurs.
5. **Dedicated table auto-persist**: document the full auto-persist logic from run-pipeline.ts. For each dedicated table:

| Dedicated Table | Triggered By Operation | Output Guard | Internal Endpoint | Failure Handling |
|---|---|---|---|---|
| `icp_job_titles` | `company.derive.icp_job_titles` | `status === "found"` && output present | `/api/internal/icp-job-titles/upsert` | try/catch, warn log, swallowed |
| `company_intel_briefings` | `company.derive.intel_briefing` | ... | ... | try/catch, swallowed |
| `person_intel_briefings` | `person.derive.intel_briefing` | ... | ... | try/catch, swallowed |
| `company_customers` | `company.research.lookup_customers` | `customers.length > 0` | ... | try/catch, swallowed |
| `gemini_icp_job_titles` | `company.derive.icp_titles_gemini` | ... | ... | try/catch, swallowed |
| `company_ads` | `company.enrich.ads_search_*` | ... | ... | try/catch, swallowed |
| `salesnav_prospects` | `person.search.sales_nav_url` | `results.length > 0` | ... | try/catch, swallowed |

Fill in the exact guards and endpoints from the code. Verify every row.

6. **Timeline event recording**: document when timeline events are created during pipeline execution. What triggers them?
7. **Entity relationship recording**: document when/how entity relationships are recorded.

##### 3d: Pipeline Completion

What happens when all steps succeed? What writes occur at pipeline completion (status update, final entity upsert, submission status sync)?

What happens when a step fails? What writes occur (step marked failed, remaining steps skipped, pipeline marked failed, submission status synced)?

---

#### Section 4: Confirmed Writes vs Auto-Persist

This section directly compares the two persistence patterns. Present them side by side:

| Aspect | Auto-Persist (run-pipeline.ts) | Confirmed Writes (dedicated workflows) |
|---|---|---|
| Error handling | try/catch, warn log, execution continues | Throws `PersistenceConfirmationError`, execution stops |
| Failure visibility | Silent — pipeline succeeds even if persist fails | Loud — pipeline fails if persist fails |
| Where defined | Inline in run-pipeline.ts per operation ID | `workflows/persistence.ts` shared module |
| Used by | Legacy generic pipeline runner | Dedicated workflow files |
| Production evidence | Multiple zero-row tables despite successful steps | Healthy dedicated tables (icp_job_titles, intel briefings) |

Name specific dedicated workflow files that use confirmed writes and specific operation IDs that still use auto-persist. Cross-reference against the operational reality check's broken tables list to show the real-world impact.

---

#### Section 5: Cumulative Context

Document the cumulative context system in detail:

1. **What it is**: the accumulated state of the pipeline entity, growing with each step's output.
2. **Where it lives**: in-memory in the Trigger.dev task function. Find the variable declaration and trace its lifecycle.
3. **How it's built**: initialized from entity input, merged after each step via `mergeContext()`. Document the merge strategy (shallow merge, new keys override).
4. **Durability**: **not durable**. If the Trigger task crashes, the cumulative context is lost. Is there any mechanism to recover it? (Check if step_results store per-step output that could be used to reconstruct it.)
5. **Freshness checking**: document the entity-state freshness check (check-freshness endpoint). When does the pipeline check if an entity's data is fresh enough to skip re-enrichment? How does the freshness response affect cumulative context?
6. **Entity state upsert as checkpoint**: when entity state is upserted mid-pipeline, does the cumulative context get persisted as part of the entity's canonical payload? If so, is this a de facto checkpoint?
7. **What happens on mid-pipeline failure**: trace the failure path. Which data from earlier successful steps is recoverable? What's lost?

---

#### Section 6: Array and Multi-Entity Results

Document how the persistence model handles operations that return multiple entities (e.g., a search returning 50 companies, or a discovery operation returning 20 locations):

1. **Current handling**: trace the code. Does the entity state upsert handle arrays? Does it iterate and create one entity per item? Or does it store the array as a single payload?
2. **Fan-out as the solution**: document how fan-out creates child pipeline runs for each entity in an array result. Each child then goes through the standard single-entity persistence path.
3. **Non-fan-out array results**: if an operation returns an array and there's no fan-out configured for it, what happens? Does the data persist or is it lost? Document specific examples.
4. **Dedicated table handling**: do any dedicated table upsert services handle arrays natively? (e.g., `upsert_company_customers()` — does it accept an array of customers?)

---

#### Section 7: Fan-Out Persistence

Document the fan-out persistence model:

1. **How fan-out works**: a parent step produces an array result, the system creates child pipeline runs (one per entity), each child executes from a later step position.
2. **What's persisted for the parent**: the parent pipeline run's step result stores the fan-out trigger output.
3. **What's persisted for each child**: each child is an independent pipeline run with its own step results, entity state upserts, and dedicated table writes.
4. **Fan-out router**: briefly document the fan-out router task that dispatches child runs to dedicated workflows vs the generic run-pipeline.
5. **Cross-reference**: how fan-out relates to entity relationships (e.g., fan-out from company to persons creates `person → works_at → company` relationships).

---

#### Section 8: Data Loss Risk Inventory

Enumerate every path where operation results can be lost. For each risk, document:
- **Risk**: what can go wrong
- **Trigger**: under what conditions
- **Impact**: what data is lost
- **Evidence**: is there production evidence of this failure mode? (cross-reference operational reality check)
- **Mitigation**: what, if anything, prevents or recovers from this

At minimum, cover these risks:

1. **Standalone execute — response-only persistence**: results only exist in the HTTP response. If the client doesn't capture them, they're gone. `operation_runs` stores the payload, but only the raw operation output — no entity upsert occurs.

2. **Silent auto-persist failure**: the try/catch pattern in run-pipeline.ts swallows dedicated table write failures. Pipeline succeeds, data doesn't persist. **Production evidence**: `company_customers` (0 rows despite 18 successful steps), `gemini_icp_job_titles` (0 rows despite 20 successful steps), `salesnav_prospects` (0 rows despite 35 successful steps).

3. **Context shape failure**: auto-persist branches guard on output shape (e.g., checking for `source_company_domain` on salesnav prospects). If the upstream operation produces a valid result but the shape doesn't match what auto-persist expects, the branch doesn't fire. **Production evidence**: `salesnav_prospects` — successful `person.search.sales_nav_url` steps don't carry `source_company_domain`.

4. **Deploy-timing landmine**: Railway must deploy before Trigger.dev. If Trigger deploys first, new internal endpoint calls hit 404s. Pipeline succeeds but internal callbacks fail silently. **Production evidence**: documented in architecture doc.

5. **Cumulative context loss on crash**: if a Trigger task crashes mid-pipeline, cumulative context (which lives only in memory) is lost. Earlier step results are persisted in `step_results`, but the merged context is not directly recoverable without replaying the merge.

6. **Entity upsert natural key collision**: two concurrent pipeline runs for the same company (same domain) could race on the entity upsert. Document what the upsert's conflict resolution strategy is (likely ON CONFLICT DO UPDATE, but verify).

7. **FMCSA ingestion — different failure mode**: FMCSA bulk writes go through a completely different path (direct batch upserts). Document the failure modes specific to this path (e.g., partial batch failures, feed_date conflicts).

Add any additional risks the executor discovers while tracing the code.

---

#### Section 9: Persistence Decision Tree

A practical reference for anyone building a new operation:

```
My operation returns a result. How do I make sure it persists?

1. Is this operation called standalone (POST /api/v1/execute only)?
   → Result is stored in operation_runs.output_payload
   → BUT no entity upsert occurs — the data is audit-only
   → If you need entity-level persistence, the operation must run inside a pipeline

2. Is this operation part of a pipeline?
   a. Does it produce a single-entity result?
      → Entity state upsert happens automatically (via entity-state/upsert internal call)
      → The result merges into cumulative context and enriches the canonical entity

   b. Does it produce a multi-entity result (array)?
      → You need a fan-out step. Without fan-out, the array is stored as a single
        payload in step_results but individual entities are NOT created.
      → With fan-out: each entity gets its own child pipeline run → individual entity upserts

   c. Does it produce data that should go to a dedicated table?
      → Option A (legacy): add an auto-persist branch in run-pipeline.ts
        ⚠ This uses the fragile try/catch pattern. Not recommended for new work.
      → Option B (recommended): create a dedicated workflow file using confirmed writes
        from workflows/persistence.ts

3. Is this a bulk ingestion operation (like FMCSA)?
   → Use the direct batch upsert pattern (see fmcsa_daily_diff_common.py)
   → Write a service function that does bulk upserts to the target table
   → Wire it to an internal endpoint
   → Call it from a Trigger.dev ingestion task
```

Expand this tree with specific code references and examples for each path.

---

#### Section 10: Table-Level Persistence Reference

A comprehensive table showing every persisted table, what writes to it, from which execution path, and the reliability of that path:

| Table | Written By | Execution Path | Reliability | Notes |
|---|---|---|---|---|
| `ops.operation_runs` | `persist_operation_execution()` | Both standalone + pipeline | Reliable | Full input/output payload |
| `ops.operation_attempts` | `persist_operation_execution()` | Both standalone + pipeline | Reliable | Per-provider attempt details |
| `ops.step_results` | Internal step-results/update | Pipeline only | Reliable | Updated per step; stores output |
| `ops.pipeline_runs` | Internal pipeline-runs/update-status | Pipeline only | Reliable | Status transitions |
| `ops.submissions` | Batch submit + status sync | Pipeline only | Reliable | Created upfront |
| `entities.company_entities` | `upsert_company_entity()` via internal endpoint | Pipeline (entity upsert step) | Reliable | Natural key: domain or LinkedIn |
| `entities.person_entities` | `upsert_person_entity()` via internal endpoint | Pipeline (entity upsert step) | Reliable | Natural key: LinkedIn or email |
| `entities.icp_job_titles` | Auto-persist OR confirmed write | Pipeline (conditional) | Mixed | Auto-persist fragile; confirmed reliable |
| `entities.company_customers` | Auto-persist only | Pipeline (conditional) | Fragile | 0 rows in production |
| `entities.salesnav_prospects` | Auto-persist only | Pipeline (conditional) | Fragile | 0 rows in production |
| ... | ... | ... | ... | ... |

Complete this table for every application table. Mark reliability as: Reliable, Mixed (both patterns exist), Fragile (auto-persist only), or N/A (not written by this system).

---

### Evidence standard

- Every claim about what gets persisted must reference a specific file and line number.
- Every claim about failure handling must show the actual try/catch or throw pattern from the code.
- Every claim about production impact must cross-reference the operational reality check.
- If the executor finds persistence behavior that contradicts existing documentation, document the discrepancy.
- If the executor discovers additional persistence paths not listed in this directive, document them.

Commit standalone.

---

## Deliverable 2: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: created `docs/PERSISTENCE_MODEL.md` covering standalone vs pipeline persistence, auto-persist vs confirmed writes, cumulative context durability, array/multi-entity handling, fan-out persistence, data loss risk inventory (N risks enumerated), and persistence decision tree. Note any surprises or discrepancies discovered.

Add a last-updated timestamp at the top of each file you create or modify, in the format `**Last updated:** 2026-03-18T[HH:MM:SS]Z`.

Commit standalone.

---

## What is NOT in scope

- **No code changes.** This is a documentation-only directive.
- **No fixes to persistence bugs.** Document them, do not fix them.
- **No schema changes.** No migrations.
- **No deploy commands.** Do not push.
- **No changes to existing documentation files** (except the work log). The persistence model doc is new and standalone.
- **No FMCSA deep-dive.** Briefly note the FMCSA bulk write pattern as a contrasting model, but do not exhaustively document every FMCSA feed's persistence path. That's a separate concern.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Guide: full path, section count, total code file references (unique files traced)
(b) Persistence paths documented: count of distinct persistence paths traced end-to-end
(c) Data loss risks: count of risks enumerated, top 3 most severe
(d) Dedicated table coverage: for each dedicated table, whether it uses auto-persist, confirmed writes, or both — and production row count evidence
(e) Surprises: any persistence behavior that contradicts existing documentation, any undocumented write paths discovered, any tables written by unexpected code paths
(f) Cumulative context finding: confirm whether cumulative context is durable or volatile, and whether mid-pipeline failure loses data from earlier steps
