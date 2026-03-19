# Executor Directive: Optional Persistence for Standalone `/api/v1/execute`

**Last updated:** 2026-03-18T23:30:00Z

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations, or take actions not covered by this directive. Within scope, use your best judgment on implementation details, type annotations, and code style consistent with the existing codebase.

**Background:** Standalone `POST /api/v1/execute` calls only persist to `operation_runs` and `operation_attempts` — the audit log. Entity table upserts (`company_entities`, `person_entities`, `job_posting_entities`) and dedicated table writes (`enigma_brand_discoveries`, `company_ads`, `gemini_icp_job_titles`, etc.) only happen inside the pipeline path (Trigger.dev → `run-pipeline.ts` → internal endpoints). This means any operation called directly via execute — ad-hoc enrichment, MCP tool calls, external integrations, testing — loses its output at the entity and intelligence layer. `docs/PERSISTENCE_MODEL.md` Section 2 documents this as "audit-only persistence," Section 8 flags it as Risk #1, and Section 9's decision tree shows the gap. This directive closes it: add opt-in `persist: bool` to standalone execute that, when true, triggers entity upsert and dedicated table writes after the operation succeeds, with errors surfaced in the response rather than silently swallowed.

---

## Existing code to read (required, in this order)

Read every file listed here before writing a line of code.

### Persistence model (start here)
- **`docs/PERSISTENCE_MODEL.md`** — full file. Key sections: Section 2 (standalone gap), Section 4 (confirmed writes vs. auto-persist), Section 8 (Risk #1), Section 9 (decision tree). This is the problem statement you are solving.

### The execute endpoint and current persistence
- **`app/routers/execute_v1.py`** — full file. Understand: `ExecuteV1Request` model (~line 255), the dispatch block (~line 332 onward). Every operation branch is identical in structure: `result = await execute_*(input_data=payload.input)` → `persist_operation_execution(...)` → `return DataEnvelope(data=result)`. There are ~86 branches. Confirm whether all branches follow this identical pattern or if any pass additional args beyond `input_data=payload.input`.
- **`app/services/operation_history.py`** — `persist_operation_execution()` (line 18–72). This writes to `ops.operation_runs` and `ops.operation_attempts`. It is not changing.

### Entity upsert — exact signatures and field extraction
- **`app/services/entity_state.py`** — full file. Critical functions:
  - `upsert_company_entity()` (~line 574): takes `org_id`, `company_id`, `canonical_fields: dict`, `entity_id=None`, `last_operation_id=None`, `last_run_id=None`, `incoming_record_version=None`. The `canonical_fields` dict is what `_company_fields_from_context()` extracts from — trace that function to understand which field names it looks for (e.g., it may fall back from `canonical_domain` → `company_domain` → `domain`).
  - `upsert_person_entity()` (~line 709): same pattern via `_person_fields_from_context()`.
  - `upsert_job_posting_entity()` (~line 831): same pattern via `_job_posting_fields_from_context()`.
  - `EntityStateVersionError`: raised on version conflict, must be caught separately.
  - **Key fact confirmed from code:** these functions take `canonical_fields` (not `cumulative_context`). For standalone execute, pass `{**input_data, **(output or {})}` as `canonical_fields` — merging input and output gives the richest possible set of identifiers.

### Internal entity-state endpoint (read to understand what NOT to use)
- **`app/routers/internal.py`** lines 1463–1540 — the existing `/api/internal/entity-state/upsert` endpoint. Note: it requires a `pipeline_run_id` and validates pipeline run exists + status is `"succeeded"`. **You cannot route through this endpoint for standalone execute** — there is no pipeline run. Call the entity upsert service functions directly.

### Auto-persist routing logic (the reference to study)
- **`trigger/src/tasks/run-pipeline.ts` lines 2110–2398** — the auto-persist branches. Study these to understand:
  - What `operation_id` values trigger dedicated table writes
  - What key in `result.output` holds the data list (e.g., `output.ads`, `output.results`, `output.customers`)
  - What fields are pulled from `cumulativeContext` vs. `result.output` — for standalone execute, `cumulativeContext` equivalent is `input_data`
  - **Do NOT copy the try/catch error-swallowing pattern** — that is the known failure mode. The Python implementation surfaces errors.

### Confirmed writes pattern (conceptual reference)
- **`trigger/src/workflows/persistence.ts`** — `confirmedInternalWrite`, `PersistenceConfirmationError`. The Python equivalent principle: every persistence step is wrapped in try/except; failures are captured and returned in the response, never swallowed.

### Dedicated table upsert services (trace each signature)
Read each to understand exact parameter names, which are required vs. optional, and what type the data list is expected as:
- `app/services/enigma_brand_discoveries.py` — `upsert_enigma_brand_discoveries()`
- `app/services/enigma_location_enrichments.py` — `upsert_enigma_location_enrichments()`
- `app/services/company_ads.py` — `upsert_company_ads()`
- `app/services/gemini_icp_job_titles.py` — `upsert_gemini_icp_job_titles()`
- `app/services/company_customers.py` — `upsert_company_customers()`
- `app/services/salesnav_prospects.py` — `upsert_salesnav_prospects()`
- `app/services/icp_job_titles.py` — `upsert_icp_job_titles()`
- `app/services/company_intel_briefings.py` — `upsert_company_intel_briefing()`
- `app/services/person_intel_briefings.py` — `upsert_person_intel_briefing()`

### Execute service functions for operations with dedicated tables
Trace these to understand the `result["output"]` shape — specifically what key holds the data list you need to pass to the upsert function:
- `app/services/company_operations.py` — `execute_company_search_enigma_brands`, `execute_company_enrich_locations`
- `app/services/adyntel_operations.py` — `execute_company_ads_search_google`, `execute_company_ads_search_meta`, `execute_company_ads_search_linkedin`
- `app/services/hq_workflow_operations.py` — `execute_company_research_icp_job_titles_gemini`, `execute_company_research_discover_customers_gemini`, `execute_company_research_lookup_customers_resolved`
- `app/services/salesnav_operations.py` — `execute_person_search_sales_nav_url`

---

## Design decisions (pre-made — do not revisit)

### D1: Opt-in via `persist: bool = False`
Add `persist: bool = False` to `ExecuteV1Request`. When `False`, behavior is identical to today — no entity upsert, no dedicated table write, no `persistence` key in the response. This preserves all existing callers. When `True`, persistence is attempted after a successful operation.

### D2: Entity upsert calls service functions directly
Do NOT route through `/api/internal/entity-state/upsert`. Call `upsert_company_entity()` / `upsert_person_entity()` / `upsert_job_posting_entity()` directly. Pass `canonical_fields={**input_data, **(output or {})}`. Pass `last_operation_id=operation_id`. Pass `last_run_id=result.get("run_id")` — this is the operation run UUID and is used as a lineage pointer.

### D3: Persistence errors are captured, not swallowed — and entity + dedicated table are independent
Both entity upsert and dedicated table write are attempted independently. If entity upsert fails, still attempt the dedicated table write (and vice versa). All results, including failures, are returned in the `persistence` key of the response.

Response shape when `persist=True` and operation succeeds (`status == "found"`):
```json
{
  "data": {
    "run_id": "...",
    "status": "found",
    "output": { ... },
    "provider_attempts": [ ... ],
    "persistence": {
      "entity_upsert": { "status": "succeeded", "entity_id": "uuid" },
      "dedicated_table": { "status": "succeeded", "table": "enigma_brand_discoveries", "rows_written": 12 }
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

Possible statuses per sub-field:
- `entity_upsert`: `"succeeded"`, `"failed"`, `"skipped"` (if entity type routing fails or no identifiable fields)
- `dedicated_table`: `"succeeded"`, `"failed"`, `"skipped"` (with `reason`: `"no_registry_entry"`, `"empty_output"`, or `"guard_failed"`)

When `persist=False` or when operation status is not `"found"`, the `persistence` key is absent from the response.

### D4: Only persist when operation status is `"found"` with non-empty output
Guard: `result.get("status") == "found" and result.get("output")`. Do not attempt persistence for `not_found`, `failed`, or `skipped` results, or when output is empty or None.

### D5: New file `app/services/persistence_routing.py`
All persistence routing logic lives in this new file: the registry dict, the handler callables, and the top-level `persist_standalone_result()` function. `execute_v1.py` only imports and calls `persist_standalone_result()`.

### D6: Handler dispatch uses a `_finalize_execute_response()` helper in execute_v1.py
Do not modify each of the ~86 dispatch branches individually. Instead, extract a helper function `_finalize_execute_response(*, auth, payload, result) -> DataEnvelope` that encapsulates the audit log write + optional persistence call + return. Replace the identical tail of every dispatch branch with a single call to this helper.

---

## Deliverable 1: Persistence routing service

Create `app/services/persistence_routing.py`.

### 1a: Result types

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass
class DedicatedTableResult:
    status: str  # "succeeded", "failed", "skipped"
    table: str | None = None
    rows_written: int | None = None
    reason: str | None = None   # populated on "skipped"
    error: str | None = None    # populated on "failed"

@dataclass
class EntityUpsertResult:
    status: str  # "succeeded", "failed", "skipped"
    entity_id: str | None = None
    error: str | None = None

@dataclass
class StandalonePersistenceResult:
    entity_upsert: EntityUpsertResult
    dedicated_table: DedicatedTableResult
```

### 1b: Dedicated table handlers

Each handler has signature:
```python
def _handle_<operation>(
    org_id: str,
    company_id: str | None,
    operation_id: str,
    output: dict[str, Any],
    input_data: dict[str, Any],
    run_id: str | None,
) -> DedicatedTableResult:
```

Handlers must:
- Extract required fields from `output` first, fall back to `input_data` for context-dependent fields (like `company_domain`) that may not be in the operation output
- Guard against missing required data: return `DedicatedTableResult(status="skipped", reason="guard_failed", ...)` if the required data list is empty or None
- Call the appropriate upsert service function
- Return `DedicatedTableResult(status="succeeded", table="...", rows_written=len(result))`
- Do NOT wrap in try/except — the caller wraps each handler invocation

**Operations to implement handlers for:**

Trace `run-pipeline.ts` lines 2110–2398 to confirm the exact output key for each — the table below is the expected mapping based on the codebase, but verify against the actual TypeScript code:

| `operation_id` | Target table | Upsert function | Data list key in output | Domain/key source |
|---|---|---|---|---|
| `company.search.enigma.brands` | `enigma_brand_discoveries` | `upsert_enigma_brand_discoveries` | `output.brands` | `discovery_prompt` from `output.prompt` or `input_data.prompt` |
| `company.enrich.locations` | `enigma_location_enrichments` | `upsert_enigma_location_enrichments` | `output.locations` | `enigma_brand_id` from `input_data.enigma_brand_id` |
| `company.ads.search.linkedin` | `company_ads` | `upsert_company_ads` (platform=`linkedin`) | `output.ads` | `company_domain` from output or `input_data.company_domain` |
| `company.ads.search.meta` | `company_ads` | `upsert_company_ads` (platform=`meta`) | `output.results` or `output.ads` (verify) | same |
| `company.ads.search.google` | `company_ads` | `upsert_company_ads` (platform=`google`) | `output.ads` (verify) | same |
| `company.research.icp_job_titles_gemini` | `gemini_icp_job_titles` | `upsert_gemini_icp_job_titles` | `output.titles` (plus title sub-lists) | `company_domain` from output or input |
| `company.research.discover_customers_gemini` | `company_customers` | `upsert_company_customers` | `output.customers` | `company_domain` from output or input; `company_entity_id` may be absent — pass `""` or skip if not resolvable |
| `company.research.lookup_customers_resolved` | `company_customers` | `upsert_company_customers` | `output.customers` | same |
| `person.search.sales_nav_url` | `salesnav_prospects` | `upsert_salesnav_prospects` | `output.results` | `source_company_domain` from output or `input_data.company_domain` |

**Notes:**
- `company.derive.icp_job_titles`, `company.derive.intel_briefing`, and `person.derive.intel_briefing` are Trigger-direct operations NOT in `SUPPORTED_OPERATION_IDS` — they cannot be called via standalone execute. Do NOT add registry entries for them. They are out of scope.
- For `company.enrich.locations`: this is in SUPPORTED_OPERATION_IDS and calls Enigma location enrichment. Verify the output shape by reading `execute_company_enrich_locations` in `company_operations.py`.
- For `company.research.icp_job_titles_gemini`: `raw_response` should be the full output dict — pass `raw_response=output`.
- Verify ALL output key names from the actual service functions before finalizing handlers. The table above is a best-effort mapping — the TypeScript `run-pipeline.ts` auto-persist branches are the authoritative reference.

### 1c: The dedicated table registry

```python
DEDICATED_TABLE_REGISTRY: dict[str, Callable] = {
    "company.search.enigma.brands": _handle_enigma_brands,
    "company.enrich.locations": _handle_enigma_locations,
    "company.ads.search.linkedin": _handle_company_ads_linkedin,
    "company.ads.search.meta": _handle_company_ads_meta,
    "company.ads.search.google": _handle_company_ads_google,
    "company.research.icp_job_titles_gemini": _handle_gemini_icp_job_titles,
    "company.research.discover_customers_gemini": _handle_company_customers,
    "company.research.lookup_customers_resolved": _handle_company_customers_resolved,
    "person.search.sales_nav_url": _handle_salesnav_prospects,
}
```

### 1d: Main entry point

```python
def persist_standalone_result(
    *,
    auth: AuthContext,
    entity_type: str,
    operation_id: str,
    input_data: dict[str, Any],
    result: dict[str, Any],
) -> StandalonePersistenceResult | None:
```

This function:

1. **Guard:** Return `None` if `result.get("status") != "found"` or if `result.get("output")` is falsy. No persistence for non-succeeded operations.

2. **Extract output:** `output = result["output"]` — a non-empty dict confirmed by the guard.

3. **Entity upsert:**
   - Build `canonical_fields = {**input_data, **output}` — merge input first, then let output keys override.
   - Route by `entity_type`:
     - `"company"` → `upsert_company_entity(org_id=auth.org_id, company_id=auth.company_id, canonical_fields=canonical_fields, last_operation_id=operation_id, last_run_id=result.get("run_id"))`
     - `"person"` → `upsert_person_entity(...)` same pattern
     - `"job"` → `upsert_job_posting_entity(...)` same pattern
   - Wrap in try/except:
     - Catch `EntityStateVersionError`: return `EntityUpsertResult(status="failed", error=str(exc))`
     - Catch any other `Exception`: log the exception, return `EntityUpsertResult(status="failed", error=str(exc))`
     - On success: return `EntityUpsertResult(status="succeeded", entity_id=upserted["entity_id"])`
     - If the upsert returns but has no `entity_id`: return `EntityUpsertResult(status="failed", error="entity upsert returned no entity_id")`

4. **Dedicated table write:**
   - Look up `operation_id` in `DEDICATED_TABLE_REGISTRY`.
   - If not found: return `DedicatedTableResult(status="skipped", reason="no_registry_entry")`
   - If found: call the handler. Wrap in try/except:
     - Catch `Exception`: log, return `DedicatedTableResult(status="failed", table=..., error=str(exc))`
     - On success: return the `DedicatedTableResult` from the handler

5. **Return:** `StandalonePersistenceResult(entity_upsert=..., dedicated_table=...)`. This function never raises.

Commit standalone.

---

## Deliverable 2: Update execute request model and handler

Modify `app/routers/execute_v1.py`.

### 2a: Request model change

Add `persist: bool = False` to `ExecuteV1Request`:

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

### 2b: `_finalize_execute_response()` helper

Add this helper function to the module (after imports, before `router`):

```python
from app.services.persistence_routing import persist_standalone_result

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
        persistence = persist_standalone_result(
            auth=auth,
            entity_type=payload.entity_type,
            operation_id=payload.operation_id,
            input_data=payload.input,
            result=result,
        )
        if persistence is not None:
            result["persistence"] = {
                "entity_upsert": {
                    "status": persistence.entity_upsert.status,
                    "entity_id": persistence.entity_upsert.entity_id,
                    "error": persistence.entity_upsert.error,
                },
                "dedicated_table": {
                    "status": persistence.dedicated_table.status,
                    "table": persistence.dedicated_table.table,
                    "rows_written": persistence.dedicated_table.rows_written,
                    "reason": persistence.dedicated_table.reason,
                    "error": persistence.dedicated_table.error,
                },
            }
    return DataEnvelope(data=result)
```

### 2c: Replace all dispatch branch endings

Every dispatch branch currently ends with:
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

Replace every occurrence with:
```python
    return _finalize_execute_response(auth=auth, payload=payload, result=result)
```

This is a mechanical find-and-replace across all ~86 branches. Verify every branch is converted and no branch still calls `persist_operation_execution()` directly.

**Important:** First verify that every dispatch branch uses the form `result = await execute_*(input_data=payload.input)` with no additional arguments. If any branch has a different pattern (e.g., passes `options` or additional context), document it in your report and handle it with a local variable or wrapper so it still flows through `_finalize_execute_response`.

Commit standalone.

---

## Deliverable 3: Tests

Create `tests/test_persistence_routing.py`.

All database calls must be mocked. Do not write to the database. Do not call real APIs.

Required test cases:

1. `test_persist_skips_when_status_not_found` — `result["status"] = "not_found"` → returns `None`, no upsert called.
2. `test_persist_skips_when_output_empty` — `result["status"] = "found"` but `result["output"] = {}` → returns `None`.
3. `test_entity_upsert_company_routes_correctly` — `entity_type="company"`, valid output → calls `upsert_company_entity`, not `upsert_person_entity`. Confirms `org_id`, `company_id`, and `last_operation_id` are passed correctly.
4. `test_entity_upsert_person_routes_correctly` — `entity_type="person"`, output with `linkedin_url` → calls `upsert_person_entity`.
5. `test_entity_upsert_version_error_captured` — `upsert_company_entity` raises `EntityStateVersionError` → `entity_upsert.status == "failed"`, dedicated table write still attempted.
6. `test_entity_upsert_arbitrary_exception_captured` — `upsert_company_entity` raises `RuntimeError("db down")` → `entity_upsert.status == "failed"`, `entity_upsert.error == "db down"`.
7. `test_dedicated_table_enigma_brands` — operation `company.search.enigma.brands`, output with `brands` list → `upsert_enigma_brand_discoveries` called, `dedicated_table.status == "succeeded"`, `rows_written` matches list length.
8. `test_dedicated_table_no_registry_entry` — operation `company.enrich.profile` → `dedicated_table.status == "skipped"`, `reason == "no_registry_entry"`.
9. `test_dedicated_table_guard_empty_list` — operation `company.ads.search.linkedin` with `ads = []` → `dedicated_table.status == "skipped"`, `reason == "guard_failed"`.
10. `test_dedicated_table_handler_exception_captured` — handler raises `Exception("upsert failed")` → `dedicated_table.status == "failed"`, `entity_upsert` result unaffected.
11. `test_input_data_fallback_for_domain` — operation `company.research.discover_customers_gemini` with `company_domain` absent from output but present in `input_data` → domain correctly extracted from input.
12. `test_canonical_fields_merge_order` — output key overrides input key for the same field name — confirm `{**input_data, **output}` order is correct (output wins) by testing an overlapping key.
13. `test_finalize_execute_response_no_persist` — `persist=False` → `DataEnvelope(data=result)` has no `persistence` key. `persist_operation_execution` called once.
14. `test_finalize_execute_response_with_persist_succeeded` — `persist=True`, operation `"found"` → response `data` has `persistence` key with both sub-fields.
15. `test_finalize_execute_response_with_persist_not_found` — `persist=True`, operation `"not_found"` → `persistence` key absent from response.

Commit standalone.

---

## Deliverable 4: Work log entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: added `persist: bool = False` to `ExecuteV1Request`; created `app/services/persistence_routing.py` with `DEDICATED_TABLE_REGISTRY` mapping 9 operation IDs to dedicated table handlers; entity upsert routing for company/person/job; errors surfaced in response `persistence` field rather than swallowed; `_finalize_execute_response()` helper replaces the ~86-branch tail in `execute_v1.py`; standalone execute now optionally persists to entity tables and dedicated tables.

Commit standalone.

---

## What is NOT in scope

- **No changes to `trigger/src/tasks/run-pipeline.ts`** — the auto-persist branches are not changing. The Python registry is a parallel implementation, not a replacement for the pipeline path.
- **No changes to `trigger/src/workflows/persistence.ts`** — TypeScript-side, not touched.
- **No changes to `app/routers/internal.py`** — internal endpoints are not modified. Standalone persistence calls service functions directly.
- **No changes to `app/services/entity_state.py`** — used as-is.
- **No changes to any dedicated table upsert service** — called as-is.
- **No changes to `app/services/operation_history.py`** — `persist_operation_execution()` is unchanged and still called first.
- **No registry entries for Trigger-direct operations** — `company.derive.icp_job_titles`, `company.derive.intel_briefing`, `person.derive.intel_briefing` are NOT in `SUPPORTED_OPERATION_IDS` and cannot be called via standalone execute. Do not add them to the registry.
- **No entity timeline recording** — timeline writes for standalone execute are a future enhancement.
- **No database migrations** — all target tables already exist.
- **No deploy commands.** Do not push.
- **No changes to `CLAUDE.md`** — the chief agent updates CLAUDE.md.

## Commit convention

Each deliverable is one standalone commit. Do not push.

## When done

Report back with:

(a) **Registry contents:** List each `operation_id` in `DEDICATED_TABLE_REGISTRY`, the target table, and the exact output key used to extract the data list. Confirm these match what `run-pipeline.ts` uses (or document any discrepancy if the TypeScript path uses a different key name).

(b) **Any dispatch branch exceptions:** Did all ~86 dispatch branches use the identical `execute_*(input_data=payload.input)` pattern, or were there exceptions? How were they handled?

(c) **Entity upsert with no identifiers:** What actually happens when `upsert_company_entity` receives a `canonical_fields` dict with no `canonical_domain`, no `company_domain`, and no `linkedin_url`? Does it create a nameless row, return an error, or skip gracefully? Document the actual behavior you observed.

(d) **`icp_job_titles_gemini` raw_response:** Confirm how `raw_response` is passed to `upsert_gemini_icp_job_titles` — is it the full output dict, a specific key, or something else?

(e) **Test count and coverage:** How many tests, what mocking strategy was used (patch targets).

(f) **Anything to flag:** Any operations where the output shape didn't contain the expected key, any field extraction decisions that required judgment calls, or any edge cases in the entity upsert that would benefit from follow-up.
