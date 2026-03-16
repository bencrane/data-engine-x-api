**Directive: Prospeo Account Information Endpoint**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We use the Prospeo API as a primary provider for company/person search and enrichment. Prospeo exposes a free `GET /account-information` endpoint that returns current plan, remaining credits, used credits, team members, and next renewal date. We need an endpoint that calls this and returns the result, so we can monitor credit consumption without logging into the Prospeo dashboard.

**The Prospeo endpoint:**

```
GET https://api.prospeo.io/account-information
Headers: X-KEY: <PROSPEO_API_KEY>
No request body.

Response (200):
{
    "error": false,
    "response": {
        "current_plan": "STARTER",
        "current_team_members": 1,
        "remaining_credits": 99,
        "used_credits": 1,
        "next_quota_renewal_days": 25,
        "next_quota_renewal_date": "2023-06-18 20:52:28+00:00"
    }
}

Error codes:
- 401 INVALID_API_KEY
- 429 RATE_LIMITED
- 400 INVALID_REQUEST / INTERNAL_ERROR
```

**Existing code to read:**

- `app/providers/prospeo.py` — existing Prospeo adapter (follow the same httpx + error handling pattern)
- `app/providers/common.py` — `ProviderAdapterResult`, `now_ms`, `parse_json_or_raw`
- `app/config.py` — `prospeo_api_key` (line 37)
- `app/routers/entities_v1.py` — `_resolve_flexible_auth` pattern (lines 40-50), router registration, `DataEnvelope` response shape
- `app/routers/_responses.py` — `DataEnvelope`, `error_response`
- `app/main.py` — router registration (see how `/api/v1` routers are mounted)

---

### Deliverable 1: Provider Adapter Function

Add `get_account_information()` to `app/providers/prospeo.py`.

**Signature:** `async def get_account_information(*, api_key: str | None) -> dict[str, Any]`

Behavior:
- If `api_key` is `None` or empty, return `{"error": True, "error_message": "missing_provider_api_key"}`.
- Call `GET https://api.prospeo.io/account-information` with `X-KEY` header. Timeout: 15 seconds.
- If the response has `error: true` or HTTP status >= 400, return `{"error": True, "error_code": <code>, "http_status": <status>}`.
- On success, return the `response` object from the Prospeo payload directly, plus `"error": False`.

This is a simple pass-through — no canonical mapping needed. Do not use the `ProviderAdapterResult` shape; this is not an operation adapter.

Commit standalone.

### Deliverable 2: Endpoint

Add a new endpoint to `app/routers/entities_v1.py`:

**Endpoint:** `POST /api/v1/providers/prospeo/account`

- Auth: use `_resolve_flexible_auth` — consistent with all other `/api/v1/` endpoints. The auth context is not used to scope the query (this is a platform-level provider call), but the endpoint still requires a valid authenticated caller.
- No request body needed. Use an empty Pydantic model or no model.
- Calls `get_account_information(api_key=settings.prospeo_api_key)`.
- On success: return `DataEnvelope` wrapping the Prospeo response fields.
- On error from the adapter (e.g., missing key, API error): return `error_response` with the error details and appropriate HTTP status (502 for upstream API errors, 503 for missing API key).
- Add a new router instance (e.g., `providers_router = APIRouter()`) and register it in `app/main.py` at prefix `/api/v1`. Do not overload an existing router with an unrelated concern.

Commit standalone.

### Deliverable 3: Tests

Create `tests/test_prospeo_account_info.py`.

Test cases (mock all HTTP calls — follow whichever mocking pattern the existing tests in the repo use):

1. **Adapter success** — mock Prospeo returning a valid account-information response, verify the adapter returns the response fields with `error: False`.
2. **Adapter missing API key** — call with `api_key=None`, verify it returns `error: True` with `missing_provider_api_key`.
3. **Adapter upstream error** — mock Prospeo returning 401 `INVALID_API_KEY`, verify the adapter returns `error: True` with the error code.
4. **Endpoint success** — mock the adapter to return a successful response, call the endpoint, verify `DataEnvelope` wrapping.
5. **Endpoint missing key** — mock `settings.prospeo_api_key` as `None`, verify 503 response.

Commit standalone.

---

**What is NOT in scope:**

- No changes to existing Prospeo adapter functions (`search_companies`, `search_people`, `enrich_company`).
- No changes to any other provider adapters.
- No changes to `execute_v1.py` or any operation services.
- No deploy commands.
- No new environment variables (the `PROSPEO_API_KEY` already exists in config).

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the adapter function signature and return shape, (b) the endpoint path and auth pattern used, (c) test count and what each test covers, (d) anything to flag.
