# Directive: `job.validate.is_active` Operation + Staffing Enrichment Blueprint

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have a staffing agency product where we search for job postings (TheirStack), validate whether they're still active (Bright Data cross-reference via HQ), enrich the hiring companies, find decision-maker contacts, and get their email + phone. All enrichment operations already exist. What's missing is: (1) a `job.validate.is_active` operation that calls an HQ endpoint to check Bright Data, and (2) a blueprint definition JSON that chains the full staffing pipeline.

---

## The HQ Validation Endpoint

An endpoint already exists at HQ that this operation will call:

**Endpoint:** `POST https://api.revenueinfra.com/api/ingest/brightdata/validate-job`

**Auth:** `x-api-key` header (value from `INGEST_API_KEY` env var — but for data-engine-x calling it, we'll use a new env var `REVENUEINFRA_INGEST_API_KEY`)

**Request:**
```json
{
  "company_domain": "stripe.com",
  "job_title": "Senior Data Engineer",
  "company_name": "Stripe"
}
```

**Response:**
```json
{
  "company_domain": "stripe.com",
  "job_title": "Senior Data Engineer",
  "indeed": {
    "found": true,
    "match_count": 2,
    "any_expired": false,
    "most_recent_ingested_at": "2026-02-19T...",
    "matched_by": "domain"
  },
  "linkedin": {
    "found": true,
    "match_count": 1,
    "most_recent_ingested_at": "2026-02-19T...",
    "matched_by": "domain"
  },
  "validation_result": "active",
  "confidence": "high"
}
```

**`validation_result` values:** `"active"`, `"likely_closed"`, `"expired"`, `"unknown"`

**`confidence` values:** `"high"` (domain match), `"medium"` (company_name fallback), `"low"` (no matches)

---

## Existing code to read before starting:

- `app/providers/revenueinfra/alumni.py` — reference pattern for calling an HQ endpoint (provider adapter)
- `app/providers/revenueinfra/_common.py` — shared config (`_configured_base_url`, `_PROVIDER`, helpers)
- `app/providers/revenueinfra/__init__.py` — re-exports (add new function here)
- `app/services/research_operations.py` — reference pattern for operation service function (e.g., `execute_company_research_lookup_alumni`)
- `app/contracts/company_research.py` — reference pattern for Pydantic contracts
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/config.py` — settings class (check if `revenueinfra_ingest_api_key` exists, add if not)
- `tests/test_alumni.py` — reference pattern for tests

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/revenueinfra/validate_job.py` (new file)

Create `validate_job_active` function following the exact pattern of `alumni.py`:

```python
async def validate_job_active(
    *,
    base_url: str,
    api_key: str | None,
    company_domain: str,
    job_title: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `company_domain` or `job_title` is missing.
2. Call `POST {base_url}/api/ingest/brightdata/validate-job` with JSON body `{company_domain, job_title, company_name}`.
3. Include `x-api-key` header with the `api_key` value.
4. Timeout: 30 seconds.
5. Map response to canonical output:

```python
"mapped": {
    "validation_result": body.get("validation_result"),
    "confidence": body.get("confidence"),
    "indeed_found": body.get("indeed", {}).get("found"),
    "indeed_match_count": body.get("indeed", {}).get("match_count"),
    "indeed_any_expired": body.get("indeed", {}).get("any_expired"),
    "indeed_matched_by": body.get("indeed", {}).get("matched_by"),
    "linkedin_found": body.get("linkedin", {}).get("found"),
    "linkedin_match_count": body.get("linkedin", {}).get("match_count"),
    "linkedin_matched_by": body.get("linkedin", {}).get("matched_by"),
}
```

Handle errors same as `alumni.py`: timeout → failed, HTTP error → failed, status >= 400 → failed.

**Update `__init__.py`** to re-export `validate_job_active`.

Commit standalone with message: `add revenueinfra provider adapter for job posting validation`

---

## Deliverable 2: Contract

**File:** `app/contracts/job_validation.py` (new file)

```python
from pydantic import BaseModel


class JobValidationOutput(BaseModel):
    validation_result: str | None = None
    confidence: str | None = None
    indeed_found: bool | None = None
    indeed_match_count: int | None = None
    indeed_any_expired: bool | None = None
    indeed_matched_by: str | None = None
    linkedin_found: bool | None = None
    linkedin_match_count: int | None = None
    linkedin_matched_by: str | None = None
    source_provider: str = "revenueinfra"
```

Commit standalone with message: `add job validation contract`

---

## Deliverable 3: Service Operation

**File:** `app/services/research_operations.py` (or create `app/services/job_operations.py` — your call based on how many job operations exist)

Add:

```python
async def execute_job_validate_is_active(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction from cumulative context:**
- `company_domain` — from `input_data` or `cumulative_context.company_domain` or `cumulative_context.company_object.domain`
- `job_title` — from `input_data` or `cumulative_context.job_title`
- `company_name` — from `input_data` or `cumulative_context.company_name` or `cumulative_context.company_object.name`

The job posting's cumulative context from a prior `job.search` step will have `company_domain`, `job_title`, and `company_name` at the top level, plus `company_object` with richer data.

**Required inputs:** `company_domain` and `job_title`. Missing either → return failed with `missing_inputs`.

**Provider call:**
```python
result = await revenueinfra.validate_job_active(
    base_url=settings.revenueinfra_api_url,
    api_key=settings.revenueinfra_ingest_api_key,
    company_domain=company_domain,
    job_title=job_title,
    company_name=company_name,
)
```

**Validate output** with `JobValidationOutput` contract. Follow the exact attempt tracking + status derivation pattern from `execute_company_research_lookup_alumni`.

**Operation ID:** `"job.validate.is_active"`

Commit standalone with message: `add job.validate.is_active operation service`

---

## Deliverable 4: Config + Router Wiring

### Config

**File:** `app/config.py`

Check if `revenueinfra_ingest_api_key` exists in the Settings class. If not, add it:

```python
revenueinfra_ingest_api_key: str | None = None
```

This is the API key data-engine-x uses to authenticate against the HQ ingest endpoints. Env var: `REVENUEINFRA_INGEST_API_KEY`.

### Router

**File:** `app/routers/execute_v1.py`

1. Add `"job.validate.is_active"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_job_validate_is_active`.
3. Add dispatch branch (follow existing pattern):

```python
if payload.operation_id == "job.validate.is_active":
    result = await execute_job_validate_is_active(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Place near the other job operations.

Commit standalone with message: `wire job.validate.is_active into config and execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_job_validate.py` (new file)

Follow the pattern from `tests/test_alumni.py`.

### Required test cases:

1. `test_validate_job_active_missing_domain` — missing company_domain → failed with missing_inputs
2. `test_validate_job_active_missing_title` — missing job_title → failed with missing_inputs
3. `test_validate_job_active_success_active` — mock HQ response with `validation_result: "active"` → status "found", output has all fields
4. `test_validate_job_active_success_expired` — mock HQ response with `validation_result: "expired"` → status "found", output.validation_result == "expired"
5. `test_validate_job_active_success_unknown` — mock HQ response with `validation_result: "unknown"` → status "found"
6. `test_validate_job_active_api_error` — mock HTTP 500 → status "failed"
7. `test_validate_job_active_timeout` — mock timeout → status "failed"
8. `test_validate_job_active_reads_from_cumulative_context` — verify inputs are extracted from `cumulative_context.company_domain`, `cumulative_context.job_title`, `cumulative_context.company_name`
9. `test_validate_job_active_reads_from_company_object` — verify `company_domain` fallback from `cumulative_context.company_object.domain`

Mock all HTTP calls. Use realistic data.

Commit standalone with message: `add tests for job.validate.is_active operation`

---

## Deliverable 6: Blueprint Definition JSON

**File:** `docs/blueprints/staffing_enrichment_v1.json` (new file — documentation only, not executed)

This is the blueprint step sequence for the staffing enrichment pipeline. Document it as a JSON file so it can be submitted via the API.

```json
{
  "name": "Staffing Enrichment v1",
  "description": "Search job postings, validate active status, enrich hiring companies, find decision-maker contacts with verified email and phone.",
  "entity_type": "job",
  "steps": [
    {
      "position": 1,
      "operation_id": "job.search",
      "step_config": {
        "posted_at_max_age_days": 45,
        "company_type": "direct_employer",
        "job_country_code_or": ["US"],
        "include_total_results": true,
        "limit": 100
      },
      "fan_out": true
    },
    {
      "position": 2,
      "operation_id": "job.validate.is_active",
      "step_config": {},
      "condition": {
        "exists": "company_domain"
      }
    },
    {
      "position": 3,
      "operation_id": "company.enrich.profile",
      "step_config": {},
      "condition": {
        "any": [
          {"eq": {"field": "validation_result", "value": "active"}},
          {"eq": {"field": "validation_result", "value": "unknown"}}
        ]
      }
    },
    {
      "position": 4,
      "operation_id": "person.search",
      "step_config": {
        "job_title_or": ["VP", "Director", "Head of", "Hiring Manager"],
        "limit": 5
      },
      "fan_out": true,
      "condition": {
        "exists": "company_domain"
      }
    },
    {
      "position": 5,
      "operation_id": "person.contact.resolve_email",
      "step_config": {},
      "condition": {
        "any": [
          {"exists": "linkedin_url"},
          {"exists": "work_email"}
        ]
      }
    },
    {
      "position": 6,
      "operation_id": "person.contact.verify_email",
      "step_config": {},
      "condition": {
        "exists": "work_email"
      }
    },
    {
      "position": 7,
      "operation_id": "person.contact.resolve_mobile_phone",
      "step_config": {},
      "condition": {
        "any": [
          {"exists": "linkedin_url"},
          {"exists": "full_name"}
        ]
      }
    }
  ]
}
```

**Notes on the blueprint:**
- Step 1 (`job.search`) fans out — each job posting becomes its own child pipeline run
- Step 2 (`job.validate.is_active`) checks Bright Data — only runs if `company_domain` exists in context
- Step 3 (`company.enrich.profile`) only runs if validation_result is "active" or "unknown" — expired postings are skipped
- Step 4 (`person.search`) fans out — each person becomes a grandchild pipeline run
- Steps 5-7 run per person: email → verify → phone
- The `step_config` values on step 1 are defaults — the submitter overrides `job_title_or`, location filters, etc. at submission time

**This file is documentation only.** The actual blueprint is created via `POST /api/blueprints/create` or `POST /api/super-admin/blueprints/create`.

Commit standalone with message: `add staffing enrichment blueprint definition and job.validate.is_active operation`

---

## What is NOT in scope

- No changes to existing operations (company.enrich.profile, person.search, etc.)
- No changes to the pipeline runner or entity state service
- No changes to HQ repo
- No Bright Data connector
- No deploy commands
- No CRM delivery

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and HQ endpoint it calls
(b) Contract field count
(c) Operation service input extraction logic (where it reads company_domain, job_title, company_name from)
(d) Config env var name for the HQ API key
(e) Router wiring confirmation
(f) Test count and names
(g) Blueprint step count and fan-out positions
(h) Anything to flag
