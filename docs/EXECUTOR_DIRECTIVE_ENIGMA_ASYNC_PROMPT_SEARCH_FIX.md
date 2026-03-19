# Executor Directive: Enigma Async Prompt Search Fix

**Last updated:** 2026-03-18T23:00:00Z

**Directive: Fix `search_brands_by_prompt()` to Use Async Output Mode**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The Enigma `search_brands_by_prompt()` adapter is broken. The GraphQL `search` query with a `prompt` field requires async output mode — the `SearchInput` must include an `output` spec (`{filename, format}`). Without it, the API rejects the call with "Search fields not supported for sql search." The fix requires switching the adapter to async mode: submit the query with an `output` spec, receive a `202 Accepted` response with a background task ID, poll `backgroundTask(id)` until completion, then retrieve and map the results. Additionally, the adapter should support `OPERATING_LOCATION` as an entity type (not just `BRAND`), since MCP testing confirmed that `generate_locations_segment` (which uses `OPERATING_LOCATION` + `prompt`) returns the best results for vertical discovery.

---

## Existing code to read

Read these files thoroughly before starting:

- `app/providers/enigma.py` — the entire file. This is the primary file being modified. Pay attention to:
  - `search_brands_by_prompt()` (line 919) — the broken adapter that sends `prompt` without `output`
  - `SEARCH_BRANDS_BY_PROMPT_QUERY` (line 644) — the current GraphQL query
  - `_graphql_post()` (line 388) — the shared GraphQL HTTP helper; note it currently only handles 200 responses and extracts `_first_brand()`. Your async flow needs different response handling.
  - `_map_operating_location()` (line 354) — existing mapper for `OperatingLocation` nodes
  - `_map_enriched_location()` (line 849) — enriched location mapper with contacts
  - `_build_locations_enriched_query()` (line 678) — dynamic query builder for enriched locations
- `docs/api-reference-docs/enigma/08-reference/02-graphql-api-reference.md` — the GraphQL SDL. Read these sections specifically:
  - `SearchInput` (line 1150) — `prompt`, `output`, `entityType` fields
  - `OutputSpec` (line 1307) — `filename: String`, `format: OutputFormat`
  - `OutputFormat` (line 1312) — `PARQUET`, `CSV`
  - `BackgroundTask` (line 305) — `id`, `status`, `result`, `lastError`, `executionAttempts`, `createdTimestamp`, `updatedTimestamp`
  - `Query.backgroundTask(id: String!)` (line 1040) — the polling query
  - Segmentation example (line 1549-1580) — shows `prompt` + `output` pattern, `202 Accepted` response, and `backgroundTask` polling
  - Status values (line 1580): `PROCESSING`, `CANCELLED`, `FAILED`, `SUCCESS`
  - `OperatingLocation` type (line 835) — connections: `names`, `addresses`, `phoneNumbers`, `brands`, `roles`, `operatingStatuses`, `websites`, `reviewSummaries`, `ranks`, `cardTransactions`
  - `SearchUnion` (line 1168) — `LegalEntity | Brand | OperatingLocation`
  - `EntityType` enum (line 681) — `BRAND`, `OPERATING_LOCATION`, `LEGAL_ENTITY`
  - Best practices note (line 1585): `search` requires either `id`/`name`/`website`; or `prompt` with `output`
- `trigger/src/workflows/parallel-deep-research.ts` — the existing async polling pattern to study and adapt. Pay attention to:
  - The create-poll-retrieve lifecycle pattern
  - `resolvePollingSchedule()` and `getPollingDelayMs()` (lines 113-128) — configurable polling with schedule array
  - `DEFAULT_PARALLEL_POLLING_SCHEDULE_MS` (line 45) — `[5000, 10000, 15000, 30000, 60000]`
  - `maxWaitMs` timeout pattern (lines 307-318)
  - Structured error handling with phase tracking
  - The overall flow: submit → get task ID → poll status → retrieve result
- `trigger/src/workflows/enigma-smb-discovery.ts` — the Trigger.dev workflow that calls brand discovery. Read how step 1 (line 489-607) calls `executeOperation()` with the discovery operation. This workflow currently expects synchronous results.
- `app/contracts/company_enrich.py` — the `EnigmaBrandDiscoveryOutput` and `EnigmaBrandItem` contracts (lines 187-202). Also `EnigmaLocationItem` (line 163) for location result mapping.
- `app/services/company_operations.py` — find `execute_company_search_enigma_brands()`. This is the service function that calls `search_brands_by_prompt()`. It passes through the adapter result.
- `docs/ENIGMA_API_REFERENCE.md` — sections on segmentation (search for "segment"), background tasks, and the `202 Accepted` status code.

---

### Deliverable 1: Async Search Adapter with Background Task Polling

Rewrite `search_brands_by_prompt()` in `app/providers/enigma.py` to use the async output mode required for prompt-based search.

**What must change:**

**1a. SearchInput must include `output` when using `prompt`:**

The `search_input` dict (currently at line 953-957) must include:

```python
search_input["output"] = {
    "filename": f"dex_brand_search_{uuid4().hex[:12]}",
    "format": "CSV",
}
```

Use a unique filename per call to avoid collisions. `uuid4().hex[:12]` or similar is fine.

**1b. Handle the `202 Accepted` response:**

The current code sends the request and immediately parses `data.search` from the response body. With `output` in the SearchInput, the API returns HTTP `202 Accepted` with a JSON body containing the background task ID. The executor must:

1. Submit the GraphQL `search` query with `output` in the `SearchInput`.
2. Check the HTTP status code. If `202`, extract the background task ID from the response body. The response shape for a `202` is a JSON object — the executor should inspect the response to find the task ID. Based on the `BackgroundTask` type in the SDL, look for an `id` field. If the exact `202` response shape is ambiguous, log the full response body on the first call and extract the ID field. Flag in the report if the shape was different than expected.
3. If the response is `200` (immediate results), handle it as the current code does — this is a fallback for cases where the API returns results synchronously.

**1c. Poll `backgroundTask(id)` until terminal status:**

After receiving the task ID, poll using a new GraphQL query:

```graphql
query PollBackgroundTask($taskId: String!) {
  backgroundTask(id: $taskId) {
    id
    status
    result
    lastError
    executionAttempts
    createdTimestamp
    updatedTimestamp
  }
}
```

Terminal statuses (from the SDL docs line 1580): `SUCCESS`, `FAILED`, `CANCELLED`.
Non-terminal status: `PROCESSING`.

**Polling parameters (configurable with defaults):**

| Parameter | Default | Purpose |
|---|---|---|
| `polling_interval_ms` | `5000` | Initial delay between polls |
| `max_wait_ms` | `300000` (5 min) | Total max wait time before timeout |
| `polling_backoff_schedule` | `[5000, 10000, 15000, 30000, 60000]` | Progressive delay schedule (same pattern as `DEFAULT_PARALLEL_POLLING_SCHEDULE_MS` in `parallel-deep-research.ts`) |

The polling loop should:
- Wait `polling_backoff_schedule[poll_index]` ms between polls (clamping to the last value when `poll_index` exceeds the array length — same as `getPollingDelayMs()` in `parallel-deep-research.ts`)
- Check accumulated wait time against `max_wait_ms`; if exceeded, return a `failed` attempt with `"timeout_waiting_for_background_task"` as the failure reason
- On `FAILED` or `CANCELLED`, return a `failed` attempt with the `lastError` from the task
- On `SUCCESS`, proceed to result retrieval

Use `asyncio.sleep()` for the delay (this is a Python `async def` function).

**1d. Retrieve and parse results on SUCCESS:**

When the background task reaches `SUCCESS`, the `result` field on `BackgroundTask` contains the output. Based on the SDL, `result` is typed as `JSON`. The executor should determine the result shape:

- **If `result` contains a URL** (e.g., an S3 pre-signed URL for the CSV output): fetch the CSV, parse it, and map rows to the existing brand/location format.
- **If `result` contains inline data** (e.g., the same `[SearchUnion]` array that a synchronous search would return): map it using the existing brand/location parsing logic.
- **If the result shape is unclear from the SDL alone**, the executor should implement both paths: check if `result` is a string (URL) or a list/dict (inline data), and handle accordingly. Flag the actual result shape in the report.

Map the results to the same output format the current synchronous code produces — a list of brand dicts or location dicts depending on entity type (see Deliverable 2).

**1e. Do NOT use `_graphql_post()` for the async flow.**

The existing `_graphql_post()` helper assumes synchronous `200` responses, calls `_first_brand()`, and returns a `(attempt, brand, is_terminal)` tuple. The async flow needs different response handling. Write a new private helper (e.g., `_graphql_post_async()`) or handle the HTTP calls inline within the adapter. Keep `_graphql_post()` unchanged for the other adapters that use it (`match_business`, `get_card_analytics`, `get_brand_locations`, `get_locations_enriched`).

**1f. Attempt tracking:**

The returned `attempt` dict must include:
- `provider: "enigma"`
- `action: "search_brands_by_prompt"` (or `"search_locations_by_prompt"` when using `OPERATING_LOCATION` — see Deliverable 2)
- `duration_ms`: total wall-clock time including polling
- `status`: `"found"` / `"not_found"` / `"failed"` / `"skipped"`
- `raw_response`: the final result payload (not every poll response)
- `background_task_id`: the task ID (if async mode was used)
- `poll_count`: number of polls performed
- `background_task_status`: terminal status of the background task

Commit standalone.

---

### Deliverable 2: Support `OPERATING_LOCATION` Entity Type

Add an `entity_type` parameter to `search_brands_by_prompt()` that controls the `entityType` in the `SearchInput`.

**Function signature change:**

```python
async def search_brands_by_prompt(
    *,
    api_key: str | None,
    prompt: str,
    entity_type: str = "BRAND",  # NEW — "BRAND" or "OPERATING_LOCATION"
    state: str | None = None,
    city: str | None = None,
    limit: int = 10,
    page_token: str | None = None,
    polling_interval_ms: int = 5000,  # from Deliverable 1
    max_wait_ms: int = 300_000,       # from Deliverable 1
) -> ProviderAdapterResult:
```

**What must change:**

**2a. Set `entityType` dynamically:**

```python
normalized_entity_type = entity_type.strip().upper() if entity_type else "BRAND"
if normalized_entity_type not in ("BRAND", "OPERATING_LOCATION"):
    normalized_entity_type = "BRAND"

search_input["entityType"] = normalized_entity_type
```

**2b. Adapt the GraphQL query for entity type:**

The current `SEARCH_BRANDS_BY_PROMPT_QUERY` uses `... on Brand { ... }` inline fragments. When `entityType` is `OPERATING_LOCATION`, the results are `OperatingLocation` nodes, not `Brand` nodes. The query needs the correct inline fragment.

Create a second query constant (or build the query dynamically) for `OPERATING_LOCATION`:

```graphql
query SearchLocationsByPrompt($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on OperatingLocation {
      id
      enigmaId
      names(first: 1) {
        edges { node { name } }
      }
      addresses(first: 1) {
        edges {
          node {
            fullAddress
            streetAddress1
            city
            state
            postalCode
          }
        }
      }
      operatingStatuses(first: 1) {
        edges { node { operatingStatus } }
      }
      phoneNumbers(first: 1) {
        edges { node { phoneNumber } }
      }
      websites(first: 1) {
        edges { node { website } }
      }
      brands(first: 1) {
        edges {
          node {
            id
            names(first: 1) {
              edges { node { name } }
            }
          }
        }
      }
    }
  }
}
```

Select the correct query based on `normalized_entity_type`.

**2c. Map results by entity type:**

- **BRAND results:** Use the existing brand mapping logic (lines 1006-1032 of the current code). Each result maps to the `EnigmaBrandItem` shape: `{enigma_brand_id, brand_name, website, location_count, industries}`.
- **OPERATING_LOCATION results:** Map each result using `_map_operating_location()` (already exists at line 354) plus additional fields (phone, website, parent brand). The mapped shape should include: `{enigma_location_id, location_name, full_address, street, city, state, postal_code, operating_status, phone, website, parent_brand_id, parent_brand_name}`.

**2d. Return format:**

The `mapped` output dict should vary by entity type:

For `BRAND`:
```python
{
    "entity_type": "BRAND",
    "brands": [...],
    "total_returned": len(brands),
    "has_next_page": ...,
    "next_page_token": ...,
}
```

For `OPERATING_LOCATION`:
```python
{
    "entity_type": "OPERATING_LOCATION",
    "locations": [...],
    "total_returned": len(locations),
    "has_next_page": ...,
    "next_page_token": ...,
}
```

**2e. Update the action name for location searches:**

When `entity_type` is `OPERATING_LOCATION`, use `action: "search_locations_by_prompt"` in the attempt dict.

**2f. Update the service function:**

In `app/services/company_operations.py`, update `execute_company_search_enigma_brands()` to pass through `entity_type` from `input_data` to the adapter. If not provided, default to `"BRAND"`.

**2g. Pagination note:**

Pagination behavior may differ in async mode — the background task may return the complete result set regardless of `limit`. The executor should check whether the async result respects the `conditions.limit` or returns all matches. If async mode returns all results, `has_next_page` should be `False` and `next_page_token` should be `None`. Document the finding in the report.

Commit standalone.

---

### Deliverable 3: Update Contracts

In `app/contracts/company_enrich.py`:

**3a.** Add an `entity_type` field to `EnigmaBrandDiscoveryOutput`:

```python
class EnigmaBrandDiscoveryOutput(BaseModel):
    entity_type: str | None = None  # NEW — "BRAND" or "OPERATING_LOCATION"
    brands: list[EnigmaBrandItem] | None = None
    locations: list[EnigmaLocationItem] | None = None  # NEW — populated when entity_type is OPERATING_LOCATION
    total_returned: int | None = None
    has_next_page: bool | None = None
    next_page_token: str | None = None
    prompt: str | None = None
    geography_filter: str | None = None
    source_provider: str = "enigma"
```

**3b.** Add `phone`, `website`, `parent_brand_id`, `parent_brand_name` fields to `EnigmaLocationItem` if not already present (check the existing definition — currently it only has address fields and `operating_status`):

```python
class EnigmaLocationItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None
    phone: str | None = None              # NEW
    website: str | None = None            # NEW
    parent_brand_id: str | None = None    # NEW
    parent_brand_name: str | None = None  # NEW
```

Commit standalone.

---

### Deliverable 4: Verify Workflow Compatibility

The Trigger.dev workflow in `trigger/src/workflows/enigma-smb-discovery.ts` calls the brand discovery operation via `executeOperation()` (line 510), which calls `/api/v1/execute`. The `/api/v1/execute` endpoint calls the Python service, which calls the adapter.

Because the async polling happens **inside the adapter** (not in the workflow), the workflow should not need changes. The adapter blocks until the background task completes and returns the final mapped result — the workflow sees the same synchronous interface.

**However**, verify:

**4a.** The adapter's total execution time with polling may exceed the default `httpx.AsyncClient` timeout or the FastAPI request timeout. The `search_brands_by_prompt()` function currently creates its own `httpx.AsyncClient(timeout=30.0)`. The polling loop runs inside the same async function. Ensure the initial request timeout is separate from the polling loop — the 30s timeout should apply to each individual HTTP call (the initial submission and each poll request), not to the overall function.

**4b.** The Trigger.dev workflow has a 300-second max task duration (from `trigger.config.ts`). With a default `max_wait_ms` of 300,000ms (5 min), the polling could approach this limit. The executor should verify that `max_wait_ms` is safely below the Trigger.dev task max duration. If 300s is the limit, consider reducing `max_wait_ms` to `240000` (4 min) to leave headroom for the rest of the workflow execution.

**4c.** Check if the workflow needs to pass `entity_type` through to the operation. Currently step 1 (line 510) sends `{ prompt, state, city, limit }`. If the workflow should support location-mode searches, the payload type `EnigmaSmBDiscoveryWorkflowPayload` would need an `entity_type` field. Add it as an optional field (defaulting to `"BRAND"`) and pass it through to the operation input. This is a small change.

If any workflow changes are needed beyond what's described here, flag them in the report but do NOT make changes that break the existing workflow behavior — all changes must be backward-compatible (default to `BRAND`).

Commit standalone.

---

### Final Deliverable: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file. This is your final commit.

---

## What is NOT in scope

- **No changes to `_graphql_post()`** — it is used by `match_business`, `get_card_analytics`, `get_brand_locations`, and `get_locations_enriched`. Do not modify it.
- **No changes to the enrichment adapters** (`get_card_analytics`, `get_brand_locations`, `get_locations_enriched`). Those work correctly with synchronous `id`-based lookups.
- **No new operations.** The existing `company.search.enigma.brands` operation ID stays the same.
- **No migrations.** The existing `enigma_brand_discoveries` and `enigma_location_enrichments` tables handle the output.
- **No changes to the persistence layer** (upsert services, internal endpoints, confirmed writes).
- **No deploy commands.** Do not push.
- **No live API calls or production testing.**

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) **Async flow:** Confirm the `output` spec is included in the `SearchInput`. Describe the exact `202` response shape observed (or inferred from the SDL). Describe how the background task ID is extracted.
(b) **Polling implementation:** Confirm the polling schedule, max wait, and terminal status handling. Note the polling delay pattern used and how it matches the Parallel.ai pattern.
(c) **Result retrieval:** Describe the `result` field shape on the `BackgroundTask` type — is it a URL, inline data, or something else? How are results mapped to the existing brand/location format?
(d) **Entity type support:** Confirm `OPERATING_LOCATION` support. Describe the GraphQL query used for location searches and the response mapping differences.
(e) **Workflow impact:** Confirm whether the workflow needed changes. If so, describe what changed. Confirm the timeout relationship between `max_wait_ms` and the Trigger.dev task max duration.
(f) **Pagination in async mode:** Does the async result respect `conditions.limit`, or does it return all matches? How is `has_next_page` computed?
(g) **Anything to flag:** Ambiguities in the `202` response shape, the `BackgroundTask.result` type, or any assumptions made.
