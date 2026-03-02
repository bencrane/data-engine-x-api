# Directive: Add Rate Limiting to BlitzAPI Provider Adapter

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** BlitzAPI requires rate limiting on all API calls. Their documentation states: "Rate limiting is mandatory. Skipping rate limiting will result in 429 Too Many Requests errors and degraded performance." Our current `app/providers/blitzapi.py` has zero rate limiting — no throttle, no retry on 429. This causes failures when multiple pipeline steps call BlitzAPI in parallel (fan-out scenarios). This directive adds retry-with-backoff on 429 responses to ALL BlitzAPI functions, and an optional per-call delay to prevent hitting the limit in the first place.

---

## Existing code to read before starting

- `app/providers/blitzapi.py` — the ONLY file you will modify. Read the entire file. There are multiple `async` functions that each make HTTP calls to BlitzAPI. ALL of them need the rate limit handling.
- `app/providers/common.py` — shared helpers (`ProviderAdapterResult`, `now_ms`, `parse_json_or_raw`)

---

## Deliverable 1: Add Rate Limit Handling to `blitzapi.py`

**File:** `app/providers/blitzapi.py`

### 1a. Add a shared retry helper

Add a private helper function at the top of the file (after the existing helpers like `_as_str`, `_as_dict`, etc.) that wraps any BlitzAPI HTTP call with retry-on-429 logic:

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

_BLITZAPI_MAX_RETRIES = 3
_BLITZAPI_BASE_DELAY_SECONDS = 2.0

async def _blitzapi_request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    json: dict[str, Any] | None = None,
) -> httpx.Response:
    """Make an HTTP request to BlitzAPI with retry on 429 (Too Many Requests).
    
    Uses exponential backoff: 2s, 4s, 8s between retries.
    """
    for attempt in range(_BLITZAPI_MAX_RETRIES + 1):
        response = await client.request(method, url, headers=headers, json=json)
        if response.status_code != 429:
            return response
        if attempt < _BLITZAPI_MAX_RETRIES:
            retry_after = response.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = _BLITZAPI_BASE_DELAY_SECONDS * (2 ** attempt)
            logger.warning(
                "BlitzAPI rate limited (429), retrying",
                extra={"attempt": attempt + 1, "delay_seconds": delay, "url": url},
            )
            await asyncio.sleep(delay)
    return response  # return last 429 response if all retries exhausted
```

### 1b. Replace all direct HTTP calls with the retry helper

Find every place in `blitzapi.py` where `client.post(...)` or `client.get(...)` is called. Replace each one with `_blitzapi_request_with_retry(client, "POST", url, headers=..., json=...)`.

The existing code pattern looks like:
```python
async with httpx.AsyncClient(timeout=...) as client:
    response = await client.post(url, headers=headers, json=payload)
```

Change to:
```python
async with httpx.AsyncClient(timeout=...) as client:
    response = await _blitzapi_request_with_retry(client, "POST", url, headers=headers, json=payload)
```

Do this for EVERY function that makes an HTTP call in the file. Do not skip any. The functions to check:
- `company_search`
- `employee_finder`
- `waterfall_icp_search`
- `resolve_mobile_phone`
- `enrich_company` (calls `company_search` internally — `company_search` handles its own retry, so `enrich_company` does not need changes)
- `resolve_linkedin_from_domain` (if it exists — it may be added by a concurrent directive)

**Do NOT change the function signatures, return types, or error handling logic of any existing function.** The only change is swapping the HTTP call method.

### 1c. Add 429 as an explicit status in error handling

In each function, after the HTTP call, if the response is still 429 after retries, return a `failed` result with a clear error:

Check if existing error handling already covers non-200 responses (it should — most functions check `response.status_code >= 400`). If so, 429 is already handled as a `failed` status after retries are exhausted. No additional changes needed.

If any function does NOT handle non-200 responses, add:
```python
if response.status_code == 429:
    return {
        "attempt": {
            "provider": "blitzapi",
            "action": action_name,
            "status": "failed",
            "error": "rate_limited_after_retries",
            "duration_ms": now_ms() - start_ms,
        },
        "mapped": None,
    }
```

Commit with message: `add retry-on-429 rate limiting to all BlitzAPI provider adapter functions`

---

## Deliverable 2: Tests

**File:** `tests/test_blitzapi_rate_limiting.py` (new file)

### Required test cases:

1. `test_retry_on_429_succeeds_on_second_attempt` — mock first call returns 429, second returns 200. Verify the function returns success (not failure).
2. `test_retry_on_429_respects_retry_after_header` — mock 429 with `retry-after: 1` header. Verify the delay is ~1 second (use time measurement or mock asyncio.sleep).
3. `test_retry_exhausted_returns_failed` — mock all calls return 429. Verify the function returns `status: "failed"` with `error` containing "rate_limited" or similar.
4. `test_non_429_errors_not_retried` — mock a 500 response. Verify it returns immediately as `failed` without retry.

Mock all HTTP calls. Test against any one of the existing BlitzAPI functions (e.g., `company_search`).

Commit with message: `add tests for BlitzAPI rate limiting retry logic`

---

## What is NOT in scope

- No changes to other provider adapters (only BlitzAPI)
- No global rate limiter or queue system
- No changes to operation services or router
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) List of ALL functions that were updated with retry logic
(b) Max retries and backoff formula
(c) How 429 with `retry-after` header is handled
(d) How exhausted retries are surfaced in the result
(e) Test count and names
(f) Anything to flag
