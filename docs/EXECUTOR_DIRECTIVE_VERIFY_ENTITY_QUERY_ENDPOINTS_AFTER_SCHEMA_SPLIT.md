# Directive: Verify Entity Query Endpoints After Schema Split

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The schema split moved entity and intelligence tables from `public` into `entities`, and `app/database.py` now contains centralized schema-aware routing for moved tables. The question for this directive is not whether the migration exists in the repo; it is whether the existing entity query endpoints actually work against production after the split. This is investigation first, fixes only if the production endpoint behavior proves something is broken. If centralized routing in `app/database.py` is doing its job, most or all of this should already work without code changes.

---

## API Surface To Verify

You must verify these production endpoints end-to-end:

- `POST /api/v1/entities/companies`
- `POST /api/v1/entities/persons`
- `POST /api/v1/entities/job-postings`
- `POST /api/v1/entities/timeline`
- `POST /api/v1/entity-relationships/query`
- `POST /api/v1/icp-job-titles/query`
- `POST /api/v1/company-customers/query`
- `POST /api/v1/company-ads/query`
- `POST /api/v1/salesnav-prospects/query`
- `POST /api/v1/icp-title-details/query`
- `POST /api/v1/company-intel-briefings/query`
- `POST /api/v1/person-intel-briefings/query`

Do **not** expand scope to other endpoints in `entities_v1.py` unless you discover they are directly implicated in a real bug in one of the endpoints above.

## Expected Production Behavior

Use `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` as the baseline for what “working correctly” means:

- Should return non-empty data:
  - `company_entities` (`88` rows)
  - `person_entities` (`503` rows)
  - `job_posting_entities` (`1` row)
  - `entity_timeline` (`4345` rows, but this endpoint requires a real `entity_id` and `entity_type`)
  - `icp_job_titles` (`156` rows)
  - `company_intel_briefings` (`3` rows)
  - `person_intel_briefings` (`1` row)
- Should correctly return empty results because the underlying tables have zero rows:
  - `entity_relationships`
  - `company_customers`
  - `salesnav_prospects`
  - `extracted_icp_job_title_details`
- `company_ads` is a special case:
  - the 2026-03-10 audit said the table was missing in prod before cleanup
  - if the target production environment now has `entities.company_ads`, the endpoint should work and likely return empty rows unless data has landed since
  - if the table is still missing in the target production environment, do **not** misdiagnose that as a query-routing bug; stop and report the environment/sequencing issue before making app-code changes

Do not treat already-broken zero-row tables as regressions introduced by the schema split. The question is whether the endpoint returns the correct response for the table’s real current state.

---

## Auth / Request Constraints You Must Respect

Do not waste time testing the wrong auth mode:

- `POST /api/v1/entities/companies` and `POST /api/v1/entities/persons` use tenant auth only (`get_current_auth`). Do not expect super-admin auth to work there.
- The other endpoints above use flexible auth and can be tested with super-admin auth, but for super-admin requests that require org scoping you must provide `org_id` in the request body where the route expects it.
- `POST /api/v1/entities/timeline` requires a real `entity_type` and `entity_id`; obtain these from prior successful entity queries rather than inventing identifiers.
- `POST /api/v1/entities/job-postings` also requires `org_id` when called as super-admin.

If an endpoint returns `401` or `403`, first verify you used the correct auth path before concluding the schema split broke it.

---

## Existing code to read

- `CLAUDE.md` — project conventions, production state, auth model, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — guardrails for investigation and fixes
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — schema split context and known architecture problems
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — expected production row counts and known broken vs healthy entity tables
- `docs/EXECUTOR_DIRECTIVE_SCHEMA_SPLIT_OPS_ENTITIES.md` — what the schema split was supposed to accomplish
- `app/database.py` — centralized schema-aware table routing
- `app/auth/dependencies.py` — tenant auth behavior
- `app/auth/super_admin.py` — super-admin auth behavior
- `app/routers/entities_v1.py` — all endpoint request models, auth mode, and query wiring for this directive
- `app/services/entity_relationships.py`
- `app/services/icp_job_titles.py`
- `app/services/company_customers.py`
- `app/services/company_ads.py`
- `app/services/salesnav_prospects.py`
- `app/services/company_intel_briefings.py`
- `app/services/person_intel_briefings.py`
- `app/services/entity_timeline.py` — if timeline behavior needs investigation beyond the router
- `app/services/entity_state.py` — if job/company/person entity lookup behavior becomes relevant during timeline verification

---

### Deliverable 1: Production Verification Matrix

Call each endpoint above against the real production API and produce a verification matrix.

Requirements:

- Use production auth that matches the endpoint’s actual auth contract.
- For each endpoint, capture:
  - auth mode used
  - request body used
  - whether the response succeeded
  - whether the response shape is correct
  - whether the data returned matches the expected production state (non-empty vs empty)
- For `/api/v1/entities/timeline`, first query a real entity from production and then call timeline for that actual entity. Do not use a fabricated ID.
- For the endpoints expected to return empty sets, verify they return clean empty data rather than `500`, schema errors, missing-table errors, or cross-schema join failures.
- If an endpoint fails, determine whether the failure is:
  - auth misuse
  - a real schema-routing bug in `app/database.py`
  - a missed direct table access path in router/service code
  - a production environment problem (for example, missing `entities.company_ads`)
  - something else

Do not make code changes before you complete this verification pass and identify a real breakage.

This deliverable is investigation only. No commit unless you discover and fix a real bug in a later deliverable.

### Deliverable 2: Fix Broken Query Paths If Needed

Only if Deliverable 1 finds a real application bug, fix it.

Scope of fixes:

- `app/database.py` if centralized schema routing is incomplete or incorrect
- `app/routers/entities_v1.py` if a route bypasses the intended schema-aware access path or mishandles auth/body requirements in a way that blocks correct production use
- the specific service module(s) backing the broken endpoint(s) if they bypass `get_supabase_client()` or otherwise target the wrong schema/table path

Constraints:

- Keep the fix narrow. Do not refactor unrelated data access patterns.
- Prefer fixing the central schema-routing abstraction if that is the real root cause, rather than patching many endpoints one by one.
- Do not introduce a global `search_path` workaround as the solution.
- Do not “fix” an environment/sequencing issue with app code. If the target production environment is missing a table or migration state it should have, report that instead.
- Do not expand this into a general audit of every table in the app. Stay on the listed endpoints only.

Commit standalone if code changes are required.

### Deliverable 3: Regression Coverage

If Deliverable 2 changed code, add or update tests that lock the fixed behavior.

At minimum, cover the exact broken access path you fixed. Good candidates include:

- schema-aware routing for moved entity tables in `app/database.py`
- representative entity-query route behavior through `entities_v1.py`
- any service module that was accidentally bypassing the schema-aware client

Do not add speculative tests for endpoints that were already working.

Commit standalone if test changes are required.

---

**What is NOT in scope:** No changes to endpoints outside the list above. No schema migrations. No deploy commands. No Trigger.dev workflow changes. No backfill of broken dedicated tables. No remediation of production data quality issues beyond making the endpoints query the correct schema. No expansion to `/api/v1/gemini-icp-job-titles/query` unless you discover it is directly implicated by the same root cause. No auth-model redesign.

**Commit convention:** If no code changes are needed, create no commit. If code changes are needed, each code-changing deliverable is one commit. Do not push.

**When done:** Report back with: (a) a per-endpoint verification matrix covering auth mode, request body, response outcome, and data/non-data result, (b) which endpoints worked unchanged, (c) which endpoints were broken and the exact root cause for each, (d) whether the problem was centralized schema routing, a missed service/router access path, auth misuse, or an environment issue, (e) every file changed to fix confirmed bugs, if any, (f) test coverage added or updated, if any, (g) anything to flag — especially whether `company_ads` is still an environment-state problem rather than an application bug.
