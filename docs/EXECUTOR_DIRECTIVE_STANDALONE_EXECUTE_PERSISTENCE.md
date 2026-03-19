# Executor Directive: Optional Persistence for Standalone `/api/v1/execute`

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Today, standalone `/api/v1/execute` calls persist results only to `operation_runs` (audit log). Entity upserts and dedicated table writes happen exclusively inside pipelines. This means any operation called outside a pipeline — MCP tool calls, ad-hoc enrichment, external integrations — loses its results at the entity level. `docs/PERSISTENCE_MODEL.md` Section 2 documents this as "audit-only persistence," Section 8 flags it as Risk #1, and Section 9's decision tree confirms the gap. This directive closes that gap by adding opt-in persistence to standalone execute, with a clean routing registry that maps operation IDs to their persistence targets.

---

## Existing code to read (required, in this order)

Read these files thoroughly before writing any code:

1. **`docs/PERSISTENCE_MODEL.md`** — the full persistence model diagnosis. Key sections:
   - Section 2 (Standalone Operation Execution) — confirms no entity upsert, no dedicated table writes, no timeline events
   - Section 4 (Confirmed Writes vs Auto-Persist) — the two patterns and their reliability characteristics
   - Section 8 (Risk #1) — this is the gap you are closing
   - Section 9 (Decision Tree) — the current persistence paths

2. **`app/routers/execute_v1.py`** — the current standalone execute endpoint. Key sections:
   - `ExecuteV1Request` (line ~243) — the request model: `operation_id`, `entity_type`, `input`, `options`, `org_id`, `company_id`
   - `execute_v1()` (line ~276) — the handler. Every operation branch follows: execute → `persist_operation_execution()` → return `DataEnvelope(data=result)`
   - Auth resolution (line ~280-291) — super-admin path builds `AuthContext` from payload `org_id`/`company_id`
   - Note how every single operation branch repeats the same 5-line pattern (execute, persist, return). There are ~70 branches.

3. **`app/services/operation_history.py`** — `persist_operation_execution()` (line 18-72). Understand exactly what it writes to `ops.operation_runs` and `ops.operation_attempts`. Note it receives the full `result` dict and stores `result.get("output")` as `output_payload`.

4. **`app/services/entity_state.py`** — entity upsert functions. Key functions:
   - `upsert_company_entity()` (line ~574) — takes `org_id`, `company_id`, `canonical_fields` (a dict), `entity_id`, `last_operation_id`, `last_run_id`. The `canonical_fields` dict is what it extracts canonical columns from via `_company_fields_from_context()` (line ~219).
   - `upsert_person_entity()` (line ~709) — same pattern, uses `_person_fields_from_context()` (line ~278).
   - `upsert_job_posting_entity()` (line ~831) — same pattern, uses `_job_posting_fields_from_context()` (line ~315).
   - **Critical:** These functions accept any dict as `canonical_fields` and extract known keys using fallback chains (e.g., `canonical_domain` or `company_domain` or `domain`). This means a standalone operation's `output` dict can be passed directly as `canonical_fields` — no mapping layer needed for entity upserts, as long as the operation output uses the same field names the extractors expect. Study the `_*_fields_from_context()` functions to understand what keys they look for.

5. **`app/routers/internal.py`** — the internal entity-state/upsert endpoint (line ~1463). Note that it requires a `pipeline_run_id` and validates the pipeline run exists and has status `"succeeded"`. **You cannot use this endpoint for standalone execute.** The entity upsert must call the service functions directly, not through the internal endpoint.

6. **`trigger/src/tasks/run-pipeline.ts` lines 2110-2398** — the auto-persist branches. Study the routing logic:
   - Each branch: `if (operationId === "X" && result.status === "found" && result.output) { ... }`
   - Each branch extracts specific fields from `result.output` and/or `cumulativeContext` to build the upsert payload
   - Each branch calls a specific internal endpoint
   - **Study the field extraction patterns — this is the knowledge you need to build the registry.** Do NOT copy the try/catch error-swallowing pattern.

7. **`trigger/src/workflows/persistence.ts`** — the confirmed writes pattern. Conceptual reference for how persistence should fail loudly. The Python implementation should follow this principle: persistence errors are captured and reported, not swallowed.

8. **All dedicated table upsert services** — read each to understand what parameters they require:
   - `app/services/icp_job_titles.py` → `upsert_icp_job_titles()` — requires `org_id`, `company_domain`, `raw_parallel_output`, optional `company_name`, `company_description`, `parallel_run_id`, `processor`, `source_submission_id`, `source_pipeline_run_id`
   - `app/services/company_intel_briefings.py` → `upsert_company_intel_briefing()` — requires `org_id`, `company_domain`, `raw_parallel_output`, optional `company_name`, client company fields, `parallel_run_id`, `processor`
   - `app/services/person_intel_briefings.py` → `upsert_person_intel_briefing()` — requires `org_id`, `person_full_name`, `raw_parallel_output`, optional person/client/customer fields
   - `app/services/company_customers.py` → `upsert_company_customers()` — requires `org_id`, `company_entity_id`, `company_domain`, `customers` list
   - `app/services/gemini_icp_job_titles.py` → `upsert_gemini_icp_job_titles()` — requires `org_id`, `company_domain`, `raw_response`, optional title lists
   - `app/services/company_ads.py` → `upsert_company_ads()` — requires `org_id`, `company_domain`, `platform`, `ads` list, `discovered_by_operation_id`
   - `app/services/salesnav_prospects.py` → `upsert_salesnav_prospects()` — requires `org_id`, `source_company_domain`, `prospects` list
   - `app/services/enigma_brand_discoveries.py` → `upsert_enigma_brand_discoveries()` — requires `org_id`, `discovery_prompt`, `brands` list
   - `app/services/enigma_location_enrichments.py` → `upsert_enigma_location_enrichments()` — requires `org_id`, `enigma_brand_id`, `locations` list

---

## Design Decisions (Pre-Made — Do Not Revisit)

These decisions are final. Implement them as stated.

### D1: Opt-in via request body

Add `persist: bool = False` to `ExecuteV1Request`. When `False`, behavior is identical to today. When `True`, the endpoint triggers entity upsert and/or dedicated table writes after the operation succeeds.

Do NOT use a `persist_options` dict for now. A simple boolean is sufficient. If we need granularity later (e.g., "persist entity but not dedicated table"), we can extend the field to accept a dict then. For now, `True` means "persist everything applicable."

### D2: Entity upsert calls service functions directly

Do NOT route through `/api/internal/entity-state/upsert` — that endpoint requires a `pipeline_run_id` and validates pipeline run status. For standalone execute, call `upsert_company_entity()` / `upsert_person_entity()` / `upsert_job_posting_entity()` directly from the persistence routing module, passing the operation's `output` dict as `canonical_fields`.

### D3: Persistence errors are captured, not swallowed

The operation result itself always returns successfully. But when `persist: true`, the response includes a `persistence` field:

```json
{
  "data": {
    "run_id": "...",
    "operation_id": "...",
    "status": "found",
    "output": { ... },
    "provider_attempts": [ ... ],
    "persistence": {
      "entity_upsert": { "status": "succeeded", "entity_id": "..." },
      "dedicated_table": { "status": "succeeded", "table": "icp_job_titles" }
    }
  }
}
```

On failure:
```json
{
  "persistence": {
    "entity_upsert": { "status": "failed", "error": "Version conflict during company entity update" },
    "dedicated_table": { "status": "skipped", "reason": "no_registry_entry" }
  }
}
```

When `persist: false` (or omitted), the `persistence` field is absent from the response.

### D4: The persistence routing registry lives in a single new file

Create `app/services/persistence_routing.py`. This file contains:
- The `DEDICATED_TABLE_REGISTRY`: a dict mapping `operation_id` → a callable that performs the dedicated table write
- The `persist_standalone_result()` function: the top-level function called by the execute handler
- All field extraction logic for building dedicated table payloads from operation output

### D5: Entity upsert uses operation output as canonical_fields

The `_*_fields_from_context()` functions in `entity_state.py` already handle flexible field name resolution (e.g., `canonical_domain` or `company_domain` or `domain`). The operation output dict can be passed directly. No mapping layer needed.

However, there is one nuance: the entity upsert functions expect `org_id`, `company_id`, `last_operation_id`, and `last_run_id` as separate parameters — these come from the auth context and the operation result, not from the output dict. The executor must pass these correctly.

### D6: Only persist when the operation succeeds

Only trigger persistence when `result.get("status")` is `"found"` and `result.get("output")` is a non-empty dict. This matches the guard conditions used by the auto-persist branches in `run-pipeline.ts`.

---

## Deliverable 1: Persistence Routing Registry

Create `app/services/persistence_routing.py`.

This file defines:

### 1a: The `DedicatedTableEntry` type

```python
@dataclass
class DedicatedTableEntry:
    table_name: str
    extract_and_write: Callable  # signature: (org_id, company_id, operation_id, output, input_data, run_id) -> dict
```

Each entry's `extract_and_write` is a function that:
- Extracts the required fields from the operation `output` dict (and `input_data` as fallback for context-dependent fields like `company_domain`)
- Calls the appropriate upsert service function
- Returns a dict with `{"status": "succeeded", "table": "<name>"}` on success
- Returns a dict with `{"status": "failed", "error": "<message>", "table": "<name>"}` on failure
- Returns a dict with `{"status": "skipped", "reason": "<guard_reason>", "table": "<name>"}` if the output doesn't contain the required data (e.g., empty list guard)

### 1b: The `DEDICATED_TABLE_REGISTRY`

A dict mapping `operation_id` strings to `DedicatedTableEntry` instances. Build entries for every operation that has a dedicated table path today:

| Operation ID | Dedicated Table | Upsert Function | Field Extraction Notes |
|---|---|---|---|
| `company.derive.icp_job_titles` | `icp_job_titles` | `upsert_icp_job_titles` | `company_domain` from `output.domain` or `output.company_domain`. `raw_parallel_output` from `output.parallel_raw_response` (needs JSON parse if string). |
| `company.derive.intel_briefing` | `company_intel_briefings` | `upsert_company_intel_briefing` | `company_domain` from `output.domain` or `output.target_company_domain`. Client fields from output directly. |
| `person.derive.intel_briefing` | `person_intel_briefings` | `upsert_person_intel_briefing` | `person_full_name` from `output.full_name` or `output.person_full_name`. Person/client/customer fields from output. |
| `company.research.discover_customers_gemini` | `company_customers` | `upsert_company_customers` | `company_domain` from `output.company_domain` or `output.domain` or `input_data.company_domain` or `input_data.domain`. `customers` list from `output.customers`. Guard: must be non-empty list. |
| `company.research.lookup_customers_resolved` | `company_customers` | `upsert_company_customers` | Same extraction as above. |
| `company.research.icp_job_titles_gemini` | `gemini_icp_job_titles` | `upsert_gemini_icp_job_titles` | `company_domain` from `output.domain` or `output.company_domain` or `input_data.company_domain`. Title lists from output. `raw_response` is the full output dict. |
| `company.ads.search.linkedin` | `company_ads` | `upsert_company_ads` | `company_domain` from `output.company_domain` or `output.domain` or `input_data.company_domain`. `platform` = `"linkedin"`. `ads` from `output.ads`. Guard: non-empty list. |
| `company.ads.search.meta` | `company_ads` | `upsert_company_ads` | Same, but `platform` = `"meta"`, `ads` from `output.results`. |
| `company.ads.search.google` | `company_ads` | `upsert_company_ads` | Same, but `platform` = `"google"`, `ads` from `output.ads`. |
| `person.search.sales_nav_url` | `salesnav_prospects` | `upsert_salesnav_prospects` | `source_company_domain` from `output.company_domain` or `output.domain` or `input_data.company_domain`. `prospects` from `output.results`. Guard: non-empty list. |
| `company.search.enigma.brands` | `enigma_brand_discoveries` | `upsert_enigma_brand_discoveries` | `discovery_prompt` from `output.prompt`. `brands` from `output.brands`. Guard: non-empty list. |

**Important extraction detail for context-dependent fields:** In the pipeline path (`run-pipeline.ts`), some fields like `company_domain` for `company_customers` and `company_ads` are pulled from `cumulativeContext`, not from the operation output. For standalone execute, there is no cumulative context. The extraction should try:
1. The operation `output` dict first (fields like `output.company_domain`, `output.domain`, `output.canonical_domain`)
2. The original `input_data` dict as fallback (the caller's input, which often contains `company_domain`)

The `input_data` fallback handles the case where an operation returns customer/ad data but doesn't echo back the company domain in its output.

**For operations not in the registry:** Dedicated table persistence is simply skipped. The `persistence.dedicated_table` field in the response should report `{"status": "skipped", "reason": "no_registry_entry"}`.

### 1c: The `persist_standalone_result()` function

```python
def persist_standalone_result(
    *,
    auth: AuthContext,
    entity_type: str,
    operation_id: str,
    input_data: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Attempt entity upsert and dedicated table write for a standalone execute result.
    Returns a persistence status dict for inclusion in the response, or None if
    the result is not eligible for persistence (not found, no output, etc.).
    """
```

This function:

1. **Guards:** Returns `None` if `result.get("status") != "found"` or `result.get("output")` is not a non-empty dict. No persistence attempted for failed/not_found/skipped results.

2. **Entity upsert:** Based on `entity_type`:
   - `"company"` → call `upsert_company_entity(org_id=auth.org_id, company_id=auth.company_id, canonical_fields=output, last_operation_id=operation_id, last_run_id=result.get("run_id"))`
   - `"person"` → call `upsert_person_entity(...)` with same pattern
   - `"job"` → call `upsert_job_posting_entity(...)` with same pattern
   - Wrap in try/except. On `EntityStateVersionError`, report `{"status": "failed", "error": str(exc)}`. On any other exception, log the error and report `{"status": "failed", "error": str(exc)}`. On success, report `{"status": "succeeded", "entity_id": upserted["entity_id"]}`.

3. **Dedicated table write:** Look up `operation_id` in `DEDICATED_TABLE_REGISTRY`. If found, call the entry's `extract_and_write` function passing `org_id=auth.org_id`, `company_id=auth.company_id`, `operation_id=operation_id`, `output=output`, `input_data=input_data`, `run_id=result.get("run_id")`. If not found, report `{"status": "skipped", "reason": "no_registry_entry"}`.

4. **Return:** A dict with `entity_upsert` and `dedicated_table` status dicts.

**Important:** Entity upsert and dedicated table writes are independent. If entity upsert fails, still attempt the dedicated table write (and vice versa). Both results are reported.

Commit standalone.

---

## Deliverable 2: Update Execute Request Model and Handler

### 2a: Update `ExecuteV1Request`

In `app/routers/execute_v1.py`, add `persist: bool = False` to `ExecuteV1Request`:

```python
class ExecuteV1Request(BaseModel):
    operation_id: str
    entity_type: Literal["person", "company", "job"]
    input: dict[str, Any]
    options: dict[str, Any] | None = None
    org_id: str | None = None
    company_id: str | None = None
    persist: bool = False  # NEW
```

### 2b: Add persistence to the execute handler

The current handler has ~70 operation branches, each following:

```python
if payload.operation_id == "X":
    result = await execute_X(input_data=payload.input)
    persist_operation_execution(auth=auth, ...)
    return DataEnvelope(data=result)
```

**Do NOT modify every branch individually.** Instead, refactor the handler to consolidate the persistence logic. Create a helper function:

```python
def _finalize_execute_response(
    *,
    auth: AuthContext,
    payload: ExecuteV1Request,
    result: dict[str, Any],
) -> DataEnvelope:
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    if payload.persist:
        persistence_result = persist_standalone_result(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_data=payload.input,
            result=result,
        )
        if persistence_result is not None:
            result["persistence"] = persistence_result
    return DataEnvelope(data=result)
```

Then replace every instance of:
```python
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

with:
```python
    return _finalize_execute_response(auth=auth, payload=payload, result=result)
```

This is a mechanical find-and-replace across all ~70 branches. The executor should verify every branch is converted. No branch should still call `persist_operation_execution()` directly followed by `return DataEnvelope()`.

**Import needed:** Add `from app.services.persistence_routing import persist_standalone_result` at the top of `execute_v1.py`.

Commit standalone.

---

## Deliverable 3: Tests

Create `tests/test_persistence_routing.py`.

Test cases:

1. **`test_persist_standalone_result_skips_when_not_found`** — result with `status: "not_found"` → returns `None`, no upsert called.

2. **`test_persist_standalone_result_skips_when_no_output`** — result with `status: "found"` but `output: None` → returns `None`.

3. **`test_persist_standalone_result_entity_upsert_company`** — result with `status: "found"`, `entity_type: "company"`, output containing `company_domain`, `company_name` → calls `upsert_company_entity()` with correct args, returns `entity_upsert.status == "succeeded"`.

4. **`test_persist_standalone_result_entity_upsert_person`** — same for `entity_type: "person"` with `linkedin_url`, `full_name`.

5. **`test_persist_standalone_result_entity_upsert_version_error`** — `upsert_company_entity()` raises `EntityStateVersionError` → `entity_upsert.status == "failed"`, dedicated table write still attempted independently.

6. **`test_persist_standalone_result_dedicated_table_icp_job_titles`** — operation `company.derive.icp_job_titles` with valid output → dedicated table write called with correct domain extraction from `output.domain`.

7. **`test_persist_standalone_result_dedicated_table_company_customers`** — operation `company.research.discover_customers_gemini` with `customers` list in output → dedicated table write called.

8. **`test_persist_standalone_result_dedicated_table_no_registry`** — operation `company.enrich.profile` (no dedicated table entry) → `dedicated_table.status == "skipped"`, `reason == "no_registry_entry"`.

9. **`test_persist_standalone_result_dedicated_table_guard_fails`** — operation `company.ads.search.linkedin` but `ads` is empty list → dedicated table write not attempted, reports skipped with guard failure reason.

10. **`test_persist_standalone_result_input_data_fallback`** — operation `company.research.discover_customers_gemini` with `company_domain` missing from output but present in `input_data` → domain correctly extracted from input fallback.

11. **`test_registry_covers_all_auto_persist_operations`** — verify that every operation ID from the auto-persist branches in `run-pipeline.ts` (the 11 operation IDs listed in the table above) has a corresponding entry in `DEDICATED_TABLE_REGISTRY`.

12. **`test_finalize_execute_response_without_persist`** — `persist=False` → response has no `persistence` field.

13. **`test_finalize_execute_response_with_persist`** — `persist=True`, successful operation → response has `persistence` field with both `entity_upsert` and `dedicated_table` status.

Mock all database calls (`upsert_company_entity`, `upsert_person_entity`, `upsert_job_posting_entity`, and all dedicated table upsert functions). Do NOT call real databases.

Commit standalone.

---

## Deliverable 4: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file. This is your final commit.

---

## What is NOT in scope

- **No changes to `trigger/src/tasks/run-pipeline.ts`** — the auto-persist branches stay as-is. The registry is a parallel implementation, not a replacement for the pipeline path (yet).
- **No changes to `trigger/src/workflows/persistence.ts`** — the confirmed writes module is TypeScript-side only. This directive is Python-side only.
- **No changes to `app/routers/internal.py`** — the internal endpoints are not modified. Standalone persistence calls service functions directly.
- **No changes to `app/services/entity_state.py`** — the entity upsert functions are used as-is.
- **No changes to any dedicated table upsert service** — the existing functions in `app/services/icp_job_titles.py`, `company_customers.py`, etc. are called as-is.
- **No changes to `app/services/operation_history.py`** — `persist_operation_execution()` continues to work exactly as before.
- **No database migrations.** No new tables, no schema changes.
- **No deploy commands.** Do not push.
- **No changes to the batch/pipeline path.** This directive only affects `/api/v1/execute`.
- **No timeline event recording for standalone execute.** This is a future enhancement, not in scope.

---

## Commit convention

Each deliverable is one commit. Do not push.

---

## When done

Report back with:

1. **Registry coverage:** List every operation ID in `DEDICATED_TABLE_REGISTRY` and confirm the field extraction matches what `run-pipeline.ts` does for each.
2. **Entity upsert compatibility:** Confirm that passing operation `output` as `canonical_fields` works without a mapping layer, citing which `_*_fields_from_context()` fallback chains cover the common output field names.
3. **Request model change:** Confirm `persist: bool = False` was added to `ExecuteV1Request` and defaults to `False`.
4. **Handler refactor:** Confirm `_finalize_execute_response()` replaced all ~70 branch endings. Report the count of branches converted.
5. **Error transparency:** Confirm persistence errors are captured and included in the response, not swallowed.
6. **Test count:** Number of test functions and confirmation all pass.
7. **Anything to flag:** Any operations where the field extraction is ambiguous or the output shape might not contain the required fields for the dedicated table write.
