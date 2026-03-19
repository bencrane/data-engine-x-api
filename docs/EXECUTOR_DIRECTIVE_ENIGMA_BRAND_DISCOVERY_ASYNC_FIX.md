# Executor Directive: Enigma Brand Discovery — Async Mode Fix

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The `search_brands_by_prompt()` adapter in `app/providers/enigma.py` is broken. The Enigma GraphQL API requires that `prompt`-based searches include an `output` spec in the `SearchInput`, which triggers async mode. Without `output`, the API rejects the call with `"Search fields not supported for sql search."` The fix is to switch the adapter to async mode: include an `OutputSpec`, handle the `202 Accepted` response, poll `backgroundTask(id)` until terminal, and retrieve results.

---

## Existing code to read (required, in this order)

1. **`app/providers/enigma.py`** — the file being fixed. Read the entire file. Key sections:
   - `SEARCH_BRANDS_BY_PROMPT_QUERY` (line ~644) — the current synchronous GraphQL query
   - `search_brands_by_prompt()` (line ~919) — the broken adapter that sends `prompt` without `output`
   - `_graphql_post()` (line ~388) — the shared GraphQL helper (currently assumes synchronous 200 responses only)
   - `_build_locations_enriched_query()` (line ~678) — the roles fragment where contact `full_name` traversal exists (already fixed in prior directive — do not re-fix)
   - `_map_enriched_location()` (line ~849) — the contact mapper (already fixed — do not re-fix)

2. **`docs/api-reference-docs/enigma/08-reference/02-graphql-api-reference.md`** — the GraphQL SDL. Study these types:
   - `SearchInput` (line ~1150): `prompt: String`, `output: OutputSpec = null`, `entityType: EntityType`
   - `OutputSpec` (line ~1307): `filename: String`, `format: OutputFormat = null`
   - `OutputFormat` (line ~1312): enum `PARQUET`, `CSV`
   - `BackgroundTask` (line ~305): `id: UUID!`, `status: String!`, `result: JSON`, `lastError: String`, `executionAttempts: Int!`, `createdTimestamp: DateTime!`, `updatedTimestamp: DateTime!`
   - `Query.backgroundTask(id: String!): BackgroundTask` (line ~1040)
   - `EntityType` enum (line ~681): `BRAND`, `OPERATING_LOCATION`, `LEGAL_ENTITY`
   - Segmentation docs (line ~1549): shows the async pattern — `output: { filename: "..." }` returns `202 Accepted` with background task ID, poll with `backgroundTask(id)`, status values: `PROCESSING`, `CANCELLED`, `FAILED`, `SUCCESS`
   - The SDL rule (line ~1585): `search requires either id/name/website; or prompt with output`

3. **`trigger/src/workflows/parallel-deep-research.ts`** — the existing Parallel.ai async polling utility. Study the pattern:
   - Configurable polling schedule (`pollingScheduleMs`) with escalating intervals
   - Max wait time (`maxWaitMs`) with timeout
   - Status polling loop with terminal state detection
   - Structured error handling with phase tracking
   - This is the reference architecture for how this codebase handles async provider calls. Your Python implementation should follow the same conceptual pattern (escalating poll intervals, configurable max wait, structured error on timeout/failure).

4. **`trigger/src/workflows/enigma-smb-discovery.ts`** — the dedicated workflow that calls the brand discovery operation. Read the full file. Key sections:
   - `executeOperation()` call at line ~510 for `BRAND_DISCOVERY_OPERATION_ID`
   - The workflow calls the operation synchronously via the internal API — it does NOT manage polling itself
   - The persistence layer at line ~305 writes discovered brands to dedicated tables

5. **`app/contracts/company_enrich.py`** — the `EnigmaBrandDiscoveryOutput` contract (line ~195). The adapter's output must continue to map to this shape.

6. **`docs/ENIGMA_API_REFERENCE.md`** — sections on segmentation, background tasks, rate limits for `generate_brands_segment` (100/day, 1000/month) and `generate_locations_segment` (100/day, 1000/month).

---

## Fix 1: Switch `search_brands_by_prompt()` to async mode

### Problem

The current adapter builds a `SearchInput` with `prompt` but no `output` field. The Enigma API requires `output` when using `prompt`-based search. The API returns an error: `"Search fields not supported for sql search."` The adapter never successfully discovers brands.

### What the async flow looks like

Per the GraphQL SDL documentation:

1. **Submit:** Send `search(searchInput: { prompt: "...", entityType: OPERATING_LOCATION, output: { filename: "unique_name" } })` — returns HTTP `202 Accepted` with a JSON body containing the background task ID.
2. **Poll:** Query `backgroundTask(id: "<task_id>")` via GraphQL until `status` reaches a terminal state (`SUCCESS`, `FAILED`, or `CANCELLED`).
3. **Retrieve:** On `SUCCESS`, the `result` field on `BackgroundTask` contains the search output (type `JSON` — the executor must determine the exact shape from the first successful call and log it).

### Implementation

#### Step 1: Add a new `_graphql_post_async()` helper

The existing `_graphql_post()` helper assumes synchronous 200 responses and extracts `_first_brand()` from the body. The async flow is fundamentally different — the submit returns a task ID, not results. Do NOT modify `_graphql_post()`. Instead, create a new helper:

```python
async def _graphql_post_async(
    *,
    api_key: str,
    action: str,
    query: str,
    variables: dict[str, Any],
    poll_interval_seconds: float = 5.0,
    max_wait_seconds: float = 300.0,
) -> tuple[dict[str, Any], dict[str, Any] | list[Any], bool]:
```

This helper must:

1. **Submit** the GraphQL query via POST to `ENIGMA_GRAPHQL_URL` (same as `_graphql_post`).
2. **Handle the 202 response:**
   - Parse the response body for the background task ID. The exact field name must be determined — it is likely in the response JSON (check for `data.backgroundTask.id`, `taskId`, `id`, or similar). Log the raw 202 response body on first encounter so the shape is captured.
   - If the response is not 202, fall back to the existing synchronous handling pattern (in case the API returns results directly for small result sets).
3. **Poll `backgroundTask(id)`** using a GraphQL query:
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
4. **Polling schedule:** Follow the Parallel.ai pattern — use escalating intervals. Start at `poll_interval_seconds`, and after 5 polls double the interval, capped at 30 seconds. Total wait capped at `max_wait_seconds` (default 5 minutes).
5. **Terminal states:** `SUCCESS`, `FAILED`, `CANCELLED`. On `FAILED` or `CANCELLED`, return a failed attempt with `lastError` from the task. On timeout, return a failed attempt with `"background_task_timeout"`.
6. **On `SUCCESS`:** Extract the `result` field from the `BackgroundTask` response. This is typed as `JSON` in the SDL — the actual shape will be either inline data or a download URL. The executor must handle both possibilities:
   - If `result` is a dict/list containing the search results directly, return them.
   - If `result` contains a URL (S3 pre-signed URL for large results, per the 302 redirect pattern documented in the API reference), fetch the URL and parse the response (CSV or JSON).
   - **Critical:** Log the raw `result` field value on first successful poll so the shape is captured for future reference. Add a comment noting the observed shape.

7. **Return signature:** Same 3-tuple pattern as `_graphql_post()` — `(attempt_dict, data, is_terminal)` — so the calling adapter code has a consistent interface.

#### Step 2: Update `search_brands_by_prompt()` to use async mode

Modify the `search_brands_by_prompt()` function:

1. **Add `output` to the `SearchInput`:**
   ```python
   import uuid

   search_input: dict[str, Any] = {
       "entityType": entity_type,  # see Fix 2 below
       "prompt": normalized_prompt,
       "output": {
           "filename": f"brand_discovery_{uuid.uuid4().hex[:12]}",
       },
       "conditions": {"limit": safe_limit},
   }
   ```
   The filename must be unique per request to avoid collisions. Use a UUID prefix.

2. **Switch to `_graphql_post_async()`** instead of the inline HTTP call. Pass `poll_interval_seconds` and `max_wait_seconds` as parameters (with sensible defaults, configurable via function parameters).

3. **Result mapping:** The response shape from the background task `result` field will differ from the current synchronous response. The current code expects `data.search` to be a list of Brand objects. The async result may be:
   - The same GraphQL response shape (just delivered asynchronously) — in which case the existing brand-mapping loop works as-is.
   - A CSV/Parquet file URL — in which case the executor must download and parse it, then map rows to the same `brands` list format.
   - A different JSON envelope — in which case the executor must adapt the mapping.

   **The executor must handle this adaptively.** Log the raw result shape, implement mapping for the most likely case (inline GraphQL response), and add a clear error with logging if the shape is unexpected so debugging is straightforward.

4. **Pagination:** In async mode, the results are likely returned as a complete dataset (not paginated). The executor should check whether the background task result contains pagination info. If the async result returns all matching results at once, set `has_next_page = False` and `next_page_token = None`. If paginated, preserve the existing offset-based pagination logic.

#### Step 3: Add function-level parameters for polling configuration

Add optional parameters to `search_brands_by_prompt()`:
```python
async def search_brands_by_prompt(
    *,
    api_key: str | None,
    prompt: str,
    entity_type: str = "BRAND",  # NEW — see Fix 2
    state: str | None = None,
    city: str | None = None,
    limit: int = 10,
    page_token: str | None = None,
    poll_interval_seconds: float = 5.0,  # NEW
    max_wait_seconds: float = 300.0,  # NEW
) -> ProviderAdapterResult:
```

---

## Fix 2: Support `OPERATING_LOCATION` entity type

### Problem

MCP testing showed that `generate_locations_segment` (which uses `entityType: OPERATING_LOCATION` with `prompt`) returns the best results for vertical discovery. The current adapter hardcodes `entityType: "BRAND"`.

### Fix

1. Add an `entity_type: str = "BRAND"` parameter to `search_brands_by_prompt()` (shown above).
2. Validate the parameter — only accept `"BRAND"` or `"OPERATING_LOCATION"`. Default to `"BRAND"` if invalid.
3. Pass the validated entity type into the `SearchInput`:
   ```python
   valid_entity_types = {"BRAND", "OPERATING_LOCATION"}
   resolved_entity_type = entity_type.upper() if entity_type and entity_type.upper() in valid_entity_types else "BRAND"
   search_input["entityType"] = resolved_entity_type
   ```
4. **Response mapping must differ by entity type:**
   - When `entityType` is `BRAND`, the response contains Brand objects — map as currently done (brand_id, brand_name, website, location_count, industries).
   - When `entityType` is `OPERATING_LOCATION`, the response contains OperatingLocation objects — map to a different shape: `enigma_location_id`, `location_name`, `full_address`, `city`, `state`, `postal_code`, `operating_status`, `website`, `phone`. Use the existing `_map_operating_location()` helper as a starting point.
5. **The output contract `EnigmaBrandDiscoveryOutput` currently has a `brands` list.** When the entity type is `OPERATING_LOCATION`, the results are locations, not brands. The executor has two options:
   - **(Preferred) Add a `locations` field** to `EnigmaBrandDiscoveryOutput` in `app/contracts/company_enrich.py` — a `list[EnigmaLocationItem] | None = None`. Populate `brands` when entity type is `BRAND`, `locations` when entity type is `OPERATING_LOCATION`. Set the unused field to `None`.
   - Or map locations into the `brands` list with adapted field names. This is less clean but avoids a contract change.

   The executor should use the preferred approach (add `locations` field).

6. **Update the GraphQL query:** The current `SEARCH_BRANDS_BY_PROMPT_QUERY` uses `... on Brand { ... }`. For `OPERATING_LOCATION`, the query needs `... on OperatingLocation { ... }`. The executor should either:
   - Build the query dynamically based on entity type (preferred), or
   - Include both fragments in the query (the API will return data for whichever type matches).

   The `OperatingLocation` fragment should request (from the SDL at line ~835):
   ```graphql
   ... on OperatingLocation {
     id
     enigmaId
     names(first: 1) { edges { node { name } } }
     addresses(first: 1) { edges { node { fullAddress streetAddress1 city state postalCode } } }
     operatingStatuses(first: 1) { edges { node { operatingStatus } } }
     websites(first: 1) { edges { node { website } } }
     phoneNumbers(first: 1) { edges { node { phoneNumber } } }
     brands(first: 1) { edges { node { id names(first: 1) { edges { node { name } } } } } }
   }
   ```

---

## Fix 3: Pagination in async mode

### Problem

The prior directive fixed pagination for synchronous mode (offset-based `pageToken`). In async mode, pagination behavior may be different — the background task may return a complete dataset.

### Fix

The executor should:
1. **Preserve the existing pagination parameters** (`limit`, `page_token`) in the `SearchInput.conditions`.
2. **After receiving the async result**, check whether the result contains pagination metadata. If yes, compute `has_next_page` and `next_page_token` as before. If the result is a complete dump, set `has_next_page = False`.
3. **Log the pagination behavior** observed in the async result so it can be documented.

---

## Fix 4: Contact `full_name` in roles fragment — ALREADY FIXED

The prior directive (`EXECUTOR_DIRECTIVE_ENIGMA_ADAPTER_PAGINATION_AND_CONTACT_NAME_FIX.md`) already fixed this. The `_build_locations_enriched_query()` roles fragment now traverses `legalEntities → persons` and extracts `fullName`/`firstName`/`lastName`. The `_map_enriched_location()` mapper populates `full_name`. **Do not modify this code.** This section is included only for context.

---

## Implementation decision: adapter-internal polling vs. workflow-managed polling

The workflow in `trigger/src/workflows/enigma-smb-discovery.ts` calls the brand discovery operation synchronously via the internal API (`POST /api/v1/execute`). There are two approaches to handle the new async nature:

**Option A (preferred): Adapter handles polling internally.** The `search_brands_by_prompt()` function in `enigma.py` handles the full async lifecycle — submit, poll, retrieve, map. The function blocks (async await) until results are ready or timeout. The workflow and operation service don't need to change. The internal API call takes longer (up to 5 minutes) but returns the same `ProviderAdapterResult` shape.

**Option B: Workflow manages polling.** The adapter returns the task ID immediately, and the Trigger.dev workflow manages the polling loop (similar to Parallel.ai). This requires changes to the workflow, the operation service, and the adapter.

**Use Option A.** The adapter already uses `httpx.AsyncClient` with async/await. The polling loop runs within the same async context. The `httpx.AsyncClient` timeout should be increased for the polling phase (the current 30-second timeout is for a single HTTP request, not the total polling duration). The workflow does not need to change, and the internal API route does not need to change. This is the simpler, more contained fix.

**Important consideration for Option A:** The FastAPI route handler that calls this adapter may have its own timeout (e.g., if called through the internal API with a request timeout). The executor should check whether the operation execution path (`/api/v1/execute` → operation service → adapter) has any intermediate timeouts that would kill the request before the 5-minute polling window completes. If so, the executor must increase those timeouts for this specific operation. Check:
- `app/routers/execute_v1.py` — any request-level timeouts
- `app/services/` — any service-level timeouts on operation execution
- The `httpx.AsyncClient` timeout in the adapter (currently 30s — this is fine for individual poll requests, but the outer function will run for minutes)

**If intermediate timeouts cannot be extended** or would create problems for other operations, fall back to Option B. But try Option A first.

---

## Rate limit awareness

Per `docs/ENIGMA_API_REFERENCE.md`, `generate_brands_segment` and `generate_locations_segment` have tight rate limits: **100/day, 1,000/month**. The adapter must:

1. Log each async search submission (including the prompt and entity type) so credit usage is trackable.
2. Not retry on `429 Slow Down` — return a failed attempt with `skip_reason: "rate_limited"`.
3. Not retry on `402 Payment Required` — return a failed attempt with `skip_reason: "insufficient_credits"`.

---

## Files to modify

| File | Change |
|---|---|
| `app/providers/enigma.py` | Add `_graphql_post_async()` helper. Modify `search_brands_by_prompt()` to use async mode with `output` spec. Add `entity_type` parameter. Add `OPERATING_LOCATION` fragment to query. Handle async result mapping for both entity types. |
| `app/contracts/company_enrich.py` | Add `locations: list[EnigmaLocationItem] \| None = None` field to `EnigmaBrandDiscoveryOutput`. Add `entity_type: str \| None = None` field to `EnigmaBrandDiscoveryOutput`. |

---

## What is NOT in scope

- **No changes to `trigger/src/workflows/enigma-smb-discovery.ts`** — the workflow calls the operation via the internal API and should not need to change (Option A).
- **No changes to `_graphql_post()`** — the existing synchronous helper is used by `match_business()`, `get_card_analytics()`, `get_brand_locations()`, and `get_locations_enriched()`. Do not touch it.
- **No changes to `_build_locations_enriched_query()` or `_map_enriched_location()`** — these are already correct from the prior directive.
- **No new operations or blueprints.** This is a fix to an existing adapter.
- **No deploy commands.** Do not push.
- **No production API calls.** Do not call the Enigma API.
- **No modifications to migration files or database schema.**

---

## Commit convention

All changes in a single commit. Do not push. Update the last-updated timestamp at the top of `app/providers/enigma.py`: `# Last updated: 2026-03-18T[HH:MM:SS]Z`.

---

## When done

Report back with:

1. **Async flow:** Confirm the `_graphql_post_async()` helper was implemented. Describe the polling schedule (intervals, max wait). Describe how the 202 response is parsed for the task ID.
2. **Result mapping:** Describe how the background task `result` field is mapped to the existing `brands` list shape. Flag if the result shape had to be assumed (it will — document the assumption clearly).
3. **Entity type support:** Confirm `OPERATING_LOCATION` is supported. Show the GraphQL fragment used. Confirm the `EnigmaBrandDiscoveryOutput` contract was updated with a `locations` field.
4. **Timeout check:** Report whether any intermediate timeouts in the operation execution path would interfere with the 5-minute polling window. If yes, describe what was changed.
5. **Rate limit handling:** Confirm 429 and 402 responses are handled without retry.
6. **Lines changed:** Approximate line count of the diff.
