**Directive: `person.resolve.from_phone` and `person.resolve.from_email` Operations**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** BlitzAPI provides two reverse-lookup endpoints that resolve a person's full LinkedIn profile from a phone number or email address. These are high-value for enrichment workflows where we have contact info but no LinkedIn URL. Both endpoints return an identical person object shape (nested at `response.person.person`), so they share the same output contract and canonical mapping. The existing `canonical_person_result()` helper in `app/providers/blitzapi.py` already handles this person shape.

**The endpoints:**

**1. Reverse Phone Lookup**
```
POST https://api.blitz-api.ai/v2/enrichment/phone-to-person
Headers: x-api-key: <key>, Content-Type: application/json
Request: {"phone": "+1234567890"}
Cost: 5 credits (on success)
```

**2. Reverse Email Lookup**
```
POST https://api.blitz-api.ai/v2/enrichment/email-to-person
Headers: x-api-key: <key>, Content-Type: application/json
Request: {"email": "antoine@blitz-agency.com"}
Cost: 1 credit (on success)
```

**Both endpoints share the same response shape:**
```json
{
  "found": true,
  "person": {
    "person": {
      "first_name": "Antoine",
      "last_name": "Blitz",
      "full_name": "Antoine Blitz",
      "nickname": null,
      "civility_title": null,
      "headline": "Founder @BlitzAPI...",
      "about_me": "...",
      "location": {
        "city": null,
        "state_code": "NY",
        "country_code": "US",
        "continent": "North America"
      },
      "linkedin_url": "https://www.linkedin.com/in/antoine-blitz-5581b7373",
      "connections_count": 500,
      "profile_picture_url": "https://media.licdn.com/dms/image/...",
      "experiences": [
        {
          "job_title": "Founder Blitzapi",
          "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
          "company_linkedin_id": "be578414-239f-522e-b2e1-9246e22a52d1",
          "job_description": "...",
          "job_start_date": "2025-05-01",
          "job_end_date": null,
          "job_is_current": true,
          "job_location": {"city": null, "state_code": null, "country_code": null}
        }
      ],
      "education": [],
      "skills": [],
      "certifications": []
    }
  }
}
```

When `found` is `false`, the `person` field is absent or null. HTTP 401 = invalid API key, 402 = insufficient credits, 500 = upstream error.

**Existing code to read:**

- `app/providers/blitzapi.py` — existing adapter functions (`phone_enrich`, `find_work_email` as pattern reference), `_blitzapi_request_with_retry()`, `canonical_person_result()` helper
- `app/services/blitzapi_person_operations.py` — existing BlitzAPI person service functions (reference pattern for input extraction, settings, output validation)
- `app/contracts/blitzapi_person.py` — existing contracts (`WaterfallIcpSearchOutput`, `EmployeeFinderOutput`, `FindWorkEmailOutput`)
- `app/services/_input_extraction.py` — `extract_person_email()` (already exists), phone extractor does not exist yet
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS`, dispatch pattern, `persist_operation_execution`

---

### Deliverable 1: Input Extraction — Phone

Add a phone extractor to `app/services/_input_extraction.py`:

1. Add an alias tuple `PERSON_PHONE = ("phone", "person_phone", "mobile_phone")` near the other `PERSON_*` tuples.
2. Add `extract_person_phone(input_data)` following the same pattern as `extract_person_email`.

Commit standalone.

### Deliverable 2: Provider Adapters

Add two new functions to `app/providers/blitzapi.py`:

**`phone_to_person(*, api_key, phone) -> ProviderAdapterResult`**
- Guard: missing `api_key` → skipped/`missing_provider_api_key`. Missing `phone` → skipped/`missing_required_inputs`.
- POST to `https://api.blitz-api.ai/v2/enrichment/phone-to-person` with `{"phone": phone}`.
- Use `_blitzapi_request_with_retry()`. Timeout: 30s.
- Action name: `"phone_to_person"`.
- On success (`found` is true and `person.person` exists): map through `canonical_person_result(person=body["person"]["person"], raw=body)` and return as `mapped`.
- On `found` false or missing person: `not_found`.
- On HTTP error: `failed` (or `not_found` for 404).

**`email_to_person(*, api_key, email) -> ProviderAdapterResult`**
- Identical pattern to `phone_to_person` but:
  - POST to `https://api.blitz-api.ai/v2/enrichment/email-to-person` with `{"email": email}`.
  - Guard on `email` instead of `phone`.
  - Action name: `"email_to_person"`.

Both adapters follow the same structure as `phone_enrich()` and `find_work_email()` in the same file, but instead of returning a single field they return the full person profile via `canonical_person_result()`.

Commit standalone.

### Deliverable 3: Output Contract

Add to `app/contracts/blitzapi_person.py` (do NOT overwrite existing models):

```python
class ReversePersonLookupOutput(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    headline: str | None = None
    current_title: str | None = None
    current_company_name: str | None = None
    current_company_domain: str | None = None
    location_name: str | None = None
    country_code: str | None = None
    source_person_id: str | None = None
    source_provider: str = "blitzapi"
```

This mirrors the fields returned by `canonical_person_result()`, minus `raw`.

Commit standalone.

### Deliverable 4: Service Operations

Add two new functions to `app/services/blitzapi_person_operations.py`:

**`execute_person_resolve_from_phone(*, input_data: dict) -> dict`**

- `operation_id = "person.resolve.from_phone"`
- Extract `phone` using `extract_person_phone(input_data)`. Missing → `failed` with `missing_inputs: ["phone"]`.
- Call `blitzapi.phone_to_person(api_key=settings.blitzapi_api_key, phone=phone)`.
- Extract `mapped` from the adapter result. The mapped dict has the `canonical_person_result` shape.
- Validate through `ReversePersonLookupOutput` (exclude `raw` — do not pass the `raw` field into the contract).
- Return standard operation result `{run_id, operation_id, status, output, provider_attempts}`.

**`execute_person_resolve_from_email(*, input_data: dict) -> dict`**

- `operation_id = "person.resolve.from_email"`
- Extract `email` using `extract_person_email(input_data)`. Missing → `failed` with `missing_inputs: ["email"]`.
- Call `blitzapi.email_to_person(api_key=settings.blitzapi_api_key, email=email)`.
- Same output validation and return shape as the phone variant.

Follow the exact same service function pattern as `execute_person_contact_resolve_email_blitzapi()` in the same file.

Commit standalone.

### Deliverable 5: Wire Into Execute Router

In `app/routers/execute_v1.py`:

1. Add `"person.resolve.from_phone"` and `"person.resolve.from_email"` to `SUPPORTED_OPERATION_IDS`.
2. Add imports for both service functions.
3. Add dispatch branches — call the service, `persist_operation_execution`, return `DataEnvelope(data=result)`.

Commit standalone.

### Deliverable 6: Tests

Create `tests/test_blitzapi_reverse_lookups.py`.

**Adapter tests (4):**

1. `test_phone_to_person_found` — Mock 200 response with `found: true` and full person object. Verify `attempt.status == "found"`, `mapped` has canonical person fields (`full_name`, `linkedin_url`, etc.).
2. `test_phone_to_person_not_found` — Mock 200 response with `found: false`. Verify `attempt.status == "not_found"`.
3. `test_email_to_person_found` — Same as phone found test but for email adapter.
4. `test_email_to_person_missing_input` — Call with `api_key` but `email=None`. Verify `attempt.status == "skipped"`, `skip_reason == "missing_required_inputs"`.

**Service tests (4):**

5. `test_service_resolve_from_phone_success` — Mock `blitzapi.phone_to_person` returning a found result. Verify `status == "found"`, output has `full_name`, `linkedin_url`, `source_provider == "blitzapi"`.
6. `test_service_resolve_from_phone_missing_input` — Call with `input_data={}`. Verify `status == "failed"`, `missing_inputs == ["phone"]`.
7. `test_service_resolve_from_email_success` — Mock `blitzapi.email_to_person` returning a found result. Same assertions as phone.
8. `test_service_resolve_from_email_missing_input` — Call with `input_data={}`. Verify `status == "failed"`, `missing_inputs == ["email"]`.

Mock all HTTP calls and provider adapters. Do not make real API calls.

Commit standalone.

---

**What is NOT in scope:**

- No changes to existing operations (`phone_enrich`, `find_work_email`, any person search operations).
- No changes to `canonical_person_result()` — reuse as-is.
- No changes to existing contracts.
- No database migrations.
- No Trigger.dev workflow changes.
- No deploy commands.
- No new environment variables (`blitzapi_api_key` already exists in settings).

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the input extractor added, (b) the two adapter function signatures and how they map the `person.person` nested response, (c) the shared output contract, (d) the two service function signatures, (e) the two operation IDs added to the router, (f) test count and what each covers, (g) anything to flag — especially if `canonical_person_result()` needed adjustment for the response shape.
