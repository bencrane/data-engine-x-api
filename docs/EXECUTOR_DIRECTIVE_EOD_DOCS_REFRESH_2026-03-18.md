# Executor Directive: End-of-Day Documentation Refresh — 2026-03-18

**Last updated:** 2026-03-18T00:00:00Z

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** A large batch of work shipped during 2026-03-18. The production-truth documentation — primarily `CLAUDE.md`, `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`, and `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md` — was written at the start of the day and does not reflect what shipped. This directive brings those files into alignment so the next agent session starts from a correct baseline.

**This is a documentation-only directive.** No code changes. No migrations. No deploys. No new SQL queries against production. The executor updates existing `.md` files and appends a work log entry. The executor must NOT run live database queries — production row counts are not being re-verified here.

---

## Files to read before making any changes

In this order, before writing a single edit:

1. `docs/EXECUTOR_WORK_LOG.md` — the authoritative record of what completed today. The work log is the source of truth. Where this directive and the work log conflict, the work log wins.
2. `CLAUDE.md` — the current production-truth routing file. Identify every section that is now stale.
3. `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` — written at 06:30 UTC today. Identify what is now out of date.
4. `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md` — the doc authority index. Identify what new docs need to be registered.
5. `docs/DEPLOY_PROTOCOL.md` — verify the migration list is current through 041.

Do not start editing until you have read all five.

---

## Summary of what shipped today

This section is for orientation only — verify every claim against `docs/EXECUTOR_WORK_LOG.md` before acting on it.

**Migrations applied to production (036–041):**
- 036: `entities.mv_fmcsa_authority_grants` — was listed as missing in the initial reality check, now exists
- 037: `entities.mv_fmcsa_insurance_cancellations` — same
- 038: `entities.mv_usaspending_contracts_typed` (14.6M rows) + `entities.mv_usaspending_first_contracts` (133K rows)
- 039: Four FMCSA analytical materialized views (`mv_fmcsa_latest_census`, `mv_fmcsa_safety_percentiles`, `mv_fmcsa_crash_counts`, `mv_fmcsa_carrier_master`); test feed rows deleted from census and crashes tables
- 040: Supplemental composite indexes on `usaspending_contracts`, `sam_gov_entities`, `sba_7a_loans`
- 041: `entities.enigma_brand_discoveries` + `entities.enigma_location_enrichments` (2 new tables, 8 indexes total)

**Bug fixes:**
- Super-admin auth gap: `/api/v1/entities/companies` and `/api/v1/entities/persons` now use `_resolve_flexible_auth` — fixed
- `run-pipeline.ts` `internalPost()`: now sends `x-internal-org-id` and `x-internal-company-id` headers — fixed

**New Enigma operations wired into `/api/v1/execute` (15 new, bringing total Enigma coverage to 17):**
- `company.search.enigma.brands`
- `company.search.enigma.aggregate`
- `company.search.enigma.person`
- `company.enrich.enigma.legal_entities`
- `company.enrich.enigma.address_deliverability`
- `company.enrich.enigma.technologies`
- `company.enrich.enigma.industries`
- `company.enrich.enigma.affiliated_brands`
- `company.enrich.enigma.marketability`
- `company.enrich.enigma.activity_flags`
- `company.enrich.enigma.bankruptcy`
- `company.enrich.enigma.watchlist`
- `person.search.enigma.roles`
- `person.enrich.enigma.profile`
- `company.verify.enigma.kyb`
- `company.enrich.locations` — extended (existing; now accepts optional Plus-tier flags)

**Standalone execute persistence (foundational capability):**
- `persist: bool = False` added to `ExecuteV1Request`
- `_finalize_execute_response()` replaced all 93 dispatch branch endings in `execute_v1.py`
- `app/services/persistence_routing.py` created — `DEDICATED_TABLE_REGISTRY` with 11 operation IDs
- When `persist=true`: entity upsert + dedicated table write attempted; errors surfaced in response, not swallowed

**New service and task files:**
- `app/services/persistence_routing.py`
- `app/services/enigma_brand_discoveries.py`
- `app/services/enigma_location_enrichments.py`
- `trigger/src/tasks/enigma-smb-discovery.ts`
- `docs/blueprints/enigma_smb_discovery_v1.json`

**New documentation files produced today:**
- `docs/AUTH_MODEL.md`
- `docs/API_SURFACE.md`
- `docs/DEPLOY_PROTOCOL.md`
- `docs/REPO_CONVENTIONS.md`
- `docs/EXECUTOR_WORK_LOG.md`
- `docs/CHIEF_AGENT_DIRECTIVE.md`
- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md`
- `docs/PERSISTENCE_MODEL.md`
- `docs/ENIGMA_INTEGRATION_AUDIT.md`
- `docs/ENIGMA_API_REFERENCE.md`
- `docs/GLOBAL_DATA_MODEL_ANALYSIS.md`
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` (the existing file was produced at 06:30 UTC; being updated here)

**Active org for new work:** Substrate (`7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19`). This org is used in the Enigma SMB Discovery blueprint but is not in `CLAUDE.md`'s Live Orgs table.

---

## Deliverable 1: Update `CLAUDE.md`

Make targeted edits only to the sections listed below. Do NOT restructure, reorder, or rewrite sections that are not explicitly identified here.

### 1a. Top-of-file timestamp

The file currently has `<!-- Last updated: 2026-03-18T07:00:00Z -->` at line 1. Update it to `<!-- Last updated: 2026-03-18T23:59:00Z -->`.

### 1b. "What Is Broken" — remove entries that are now fixed

Find and remove the bullet point about `mv_fmcsa_authority_grants` and `mv_fmcsa_insurance_cancellations`. The current text reads approximately:
> `mv_fmcsa_authority_grants` and `mv_fmcsa_insurance_cancellations` do not exist in production — migrations 036 and 037 have not been applied.

Delete this bullet. Both materialized views now exist (migrations 036 and 037 were applied today).

Do NOT remove any of these still-broken items:
- `company_customers` (0 rows)
- `gemini_icp_job_titles` (0 rows)
- `salesnav_prospects` (0 rows)
- `company_ads` (0 rows)
- `fmcsa_carrier_signals` (0 rows)
- end-to-end pipeline reliability issues

### 1c. "What Has Never Been Used" — add new Enigma operations

The 15 new Enigma operations listed in the summary above have been wired but never called in production. Add them to the never-been-used operations list. They should appear as a group — add them after the existing Enigma operations (`company.enrich.card_revenue`, `company.enrich.locations`) already listed.

The exact operation IDs to add:
```
- `company.search.enigma.brands`
- `company.search.enigma.aggregate`
- `company.search.enigma.person`
- `company.enrich.enigma.legal_entities`
- `company.enrich.enigma.address_deliverability`
- `company.enrich.enigma.technologies`
- `company.enrich.enigma.industries`
- `company.enrich.enigma.affiliated_brands`
- `company.enrich.enigma.marketability`
- `company.enrich.enigma.activity_flags`
- `company.enrich.enigma.bankruptcy`
- `company.enrich.enigma.watchlist`
- `person.search.enigma.roles`
- `person.enrich.enigma.profile`
- `company.verify.enigma.kyb`
```

Do NOT remove any existing entries from the never-used list unless you can confirm from the work log that a specific operation was used today. The Enigma operations that were already listed (`company.enrich.locations`, `company.enrich.hiring_signals`, etc.) are separate from the new Enigma operations — `company.enrich.locations` was extended today but the original non-extended form was in the list; use judgment on whether the extension makes it "no longer never-been-used." If in doubt, keep it.

Update the count: the current text says `54 executable operations ... have never been called in production`. Update this count to reflect the addition of 15 new never-called operations. New count: **69** (54 + 15). Verify this against the work log — if the work log gives a different picture, use the work log.

### 1d. "Known Architectural Problems" — update auto-persist entry

The current text under "Top 3 problems" reads:
> auto-persist silent failures: the legacy `run-pipeline.ts` wraps dedicated-table writes in try/catch and swallows failures. Dedicated workflows use confirmed writes that surface failures.

Update it to:
> auto-persist silent failures: the legacy `run-pipeline.ts` wraps dedicated-table writes in try/catch and swallows failures. Dedicated workflows use confirmed writes that surface failures. Standalone `/api/v1/execute` with `persist: true` now also surfaces persistence errors in the response (implemented 2026-03-18). The `run-pipeline.ts` auto-persist silent failures remain unresolved.

### 1e. Live Orgs table — add Substrate

The current Live Orgs table has three rows (Staffing Activation, Revenue Activation, AlumniGTM). Add a fourth:

| Org | ID | Companies |
|---|---|---|
| Substrate | `7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19` | — |

### 1f. Directory Structure — add new files

Add the following entries to the Directory Structure section under the relevant parent directory:

Under `app/services/`:
```
    - `app/services/persistence_routing.py` — DEDICATED_TABLE_REGISTRY and persist_standalone_result() for standalone execute persistence
    - `app/services/enigma_brand_discoveries.py` — array-capable upsert service for Enigma brand discovery results
    - `app/services/enigma_location_enrichments.py` — array-capable upsert service for Enigma location enrichment results
```

Under `trigger/src/tasks/`:
Update the description to note that `enigma-smb-discovery.ts` was added (dedicated Enigma SMB discovery workflow with confirmed writes).

Under `docs/`:
Add to the bullet list:
```
  - `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — auth paths, data visibility by auth type, practical access examples; grounded in code
  - `docs/PERSISTENCE_MODEL.md` — full persistence audit, 9 data loss risks, persistence decision tree
  - `docs/ENIGMA_API_REFERENCE.md` — consolidated Enigma API reference from 61 source files
  - `docs/GLOBAL_DATA_MODEL_ANALYSIS.md` — analysis of moving from org-scoped to global entity model
```

Under `docs/blueprints/`:
Note that `enigma_smb_discovery_v1.json` was added (Substrate org, 3 steps).

### 1g. Diagnostic Reports section — add new docs

The current Diagnostic Reports section lists:
```
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` - live production state audit
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` - full architecture doc including known problems
```

Add:
```
- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` - auth paths and data visibility model; grounded in code; supersedes AUTH_MODEL.md for technical detail
- `docs/PERSISTENCE_MODEL.md` - full persistence audit; 9 data loss risks; read before any persistence work
- `docs/GLOBAL_DATA_MODEL_ANALYSIS.md` - analysis of globalizing entity model; 13 sections; recommendation: hybrid approach deferred pending 4 prerequisites
```

Commit standalone: "Update CLAUDE.md to reflect end-of-day 2026-03-18 changes"

---

## Deliverable 2: Update `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`

The existing file was written at 06:30 UTC and is a production snapshot. Do NOT rewrite it. Do NOT remove existing content. Append a new section at the beginning of the file — after the `# Operational Reality Check` header and `**Last updated:**` line and before `As of 2026-03-18.` — titled:

```markdown
## Post-Audit Updates (2026-03-18, end of day)
```

This section documents what changed after the initial 06:30 UTC audit. Write it in the same factual, direct style as the rest of the document — no editorializing, no hedging.

The section must contain the following subsections:

### Subsection: Migrations Applied After Initial Audit

State that migrations 036–041 were applied to production during the day:

- **036** (`mv_fmcsa_authority_grants`): materialized view created. Was listed as missing in the "Missing Expected Tables" section below — that entry is now stale.
- **037** (`mv_fmcsa_insurance_cancellations`): materialized view created. Was listed as missing — now stale.
- **038** (`mv_usaspending_contracts_typed`, `mv_usaspending_first_contracts`): two USASpending analytical materialized views created. `mv_usaspending_contracts_typed` covers 14.6M rows with typed column casts. `mv_usaspending_first_contracts` covers 133K rows (first contract per recipient).
- **039** (four FMCSA analytical MVs): `mv_fmcsa_latest_census` (2.58M rows), `mv_fmcsa_safety_percentiles` (36K rows), `mv_fmcsa_crash_counts` (40K rows), `mv_fmcsa_carrier_master` (2.58M rows). Test feed rows were deleted from `motor_carrier_census_records` and `commercial_vehicle_crashes` tables — row counts in the audit sections below may be slightly overstated.
- **040** (supplemental indexes): composite indexes added to `usaspending_contracts`, `sam_gov_entities`, `sba_7a_loans` for analytical query performance. No row count changes.
- **041** (`enigma_brand_discoveries`, `enigma_location_enrichments`): two new tables in `entities` schema. Both currently have 0 rows (tables newly created, no operations have been run against production yet).

### Subsection: Bug Fixes

- **Super-admin auth on entity endpoints (fixed):** `/api/v1/entities/companies` and `/api/v1/entities/persons` previously used `Depends(get_current_auth)` which blocked super-admin API key with 401. Both now use `Depends(_resolve_flexible_auth)`. Super-admin can query these endpoints by passing `org_id` in the request body, consistent with all other entity query endpoints. Noted as Auth Gap #1 in `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — now resolved.
- **`run-pipeline.ts` `internalPost()` headers (fixed):** The generic `internalPost()` function was not sending `x-internal-org-id` or `x-internal-company-id` headers, unlike the `InternalApiClient` class used by dedicated workflows. Fixed — `internalPost()` now sets both headers from the pipeline payload. The existing behavior of passing org_id in the request body was preserved for backward compatibility.

### Subsection: New Operations Added

15 new Enigma operations were wired into `/api/v1/execute`, bringing total Enigma coverage to 17 operations (2 pre-existing + 15 new). All 15 new operations have 0 `operation_runs` rows in production (never called). Operation IDs:

`company.search.enigma.brands`, `company.search.enigma.aggregate`, `company.search.enigma.person`, `company.enrich.enigma.legal_entities`, `company.enrich.enigma.address_deliverability`, `company.enrich.enigma.technologies`, `company.enrich.enigma.industries`, `company.enrich.enigma.affiliated_brands`, `company.enrich.enigma.marketability`, `company.enrich.enigma.activity_flags`, `company.enrich.enigma.bankruptcy`, `company.enrich.enigma.watchlist`, `person.search.enigma.roles`, `person.enrich.enigma.profile`, `company.verify.enigma.kyb`.

### Subsection: Standalone Execute Persistence

`POST /api/v1/execute` now accepts `persist: bool = False`. When `persist=true`, the endpoint attempts entity state upsert and dedicated table writes and returns a `persistence` status field in the response. Errors are surfaced, not swallowed. `app/services/persistence_routing.py` implements a `DEDICATED_TABLE_REGISTRY` mapping 11 operation IDs to write functions. `_finalize_execute_response()` was created and replaced all 93 dispatch branch endings in `execute_v1.py`. This addresses Risk #1 from `docs/PERSISTENCE_MODEL.md` for standalone execute calls.

### Subsection: Row Counts Not Re-Verified

Row counts in the audit sections below reflect the 06:30 UTC state. They have NOT been re-verified after migrations 036–041 were applied. To get current counts:

```bash
doppler run -p data-engine-x-api -c prd -- bash -c 'psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM entities.mv_fmcsa_authority_grants;"'
```

---

Also update the `**Last updated:**` timestamp at the top of the file from `2026-03-18T06:30:00Z` to `2026-03-18T23:59:00Z`.

Commit standalone: "Append end-of-day post-audit updates to OPERATIONAL_REALITY_CHECK_2026-03-18.md"

---

## Deliverable 3: Update `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`

### 3a. Technical Reference section — add new docs

The current Technical Reference section lists:
```
- `docs/AUTH_MODEL.md`
- `docs/API_SURFACE.md`
- `docs/DEPLOY_PROTOCOL.md`
- `docs/SYSTEM_OVERVIEW.md`
```

Add the following entries:
```
- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — auth paths, data visibility by auth type, practical access examples; grounded in code; more detailed than AUTH_MODEL.md
- `docs/PERSISTENCE_MODEL.md` — full persistence audit; all write paths, data loss risks, confirmed-write vs auto-persist distinction; read before persistence work
- `docs/ENIGMA_API_REFERENCE.md` — consolidated Enigma API reference from 61 source files; read before any Enigma adapter or operation work
- `docs/GLOBAL_DATA_MODEL_ANALYSIS.md` — analysis of moving from org-scoped to global entity model; decision pending
```

### 3b. Operational section — verify EXECUTOR_WORK_LOG.md is listed

Check the Operational section. It should contain `docs/EXECUTOR_WORK_LOG.md`. If it does, no change needed. If it's missing, add it.

### 3c. Current Workstream Picture — add new workstreams

The current "Current Workstream Picture" section lists:
- dedicated workflow migration and fan-out routing
- schema split work and post-split verification
- production reliability, runtime, and deploy-sequencing investigations
- FMCSA ingestion and mapping across multiple feed families
- newer workflow families such as job-posting-led discovery

Add:
- Enigma API full coverage — 17 operations wired, dedicated workflow, 2 new persistence tables, async brand discovery
- Standalone execute persistence — persist flag, persistence routing registry, response-level error surfacing
- Global data model analysis — documentation-only analysis; hybrid approach (global entities, org-scoped dedicated tables) recommended, deferred pending prerequisites

### 3d. Last-updated timestamp

Update from `2026-03-18T07:00:00Z` to `2026-03-18T23:59:00Z`.

Commit standalone: "Update CHIEF_AGENT_DOC_AUTHORITY_MAP.md to reflect new docs and workstreams"

---

## Deliverable 4: Verify `docs/DEPLOY_PROTOCOL.md`

Read `docs/DEPLOY_PROTOCOL.md`. Confirm the migration list includes all entries through 041, specifically:
- 036 `mv_fmcsa_authority_grants` ✓
- 037 `mv_fmcsa_insurance_cancellations` ✓
- 038 `mv_usaspending_analytical` (USASpending typed base + first-contract MVs) ✓
- 039 `mv_fmcsa_analytical` (four FMCSA analytical MVs) ✓
- 040 `analytical_missing_indexes` ✓
- 041 `enigma_brand_discoveries` ✓

If any are missing or have incorrect descriptions, add or fix them. If the file is already correct, no commit is needed — note in your report that the file was verified current.

---

## Deliverable 5: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary: updated production-truth documentation to reflect all 2026-03-18 end-of-day changes — CLAUDE.md (removed stale mv_fmcsa broken entry, added 15 new Enigma operations to never-used list with updated count, updated auto-persist problem description, added Substrate to Live Orgs, added persistence_routing.py and Enigma services to Directory Structure, added new docs to Diagnostic Reports), OPERATIONAL_REALITY_CHECK_2026-03-18.md (appended post-audit section covering migrations 036–041, both bug fixes, new operations, and standalone execute persistence), CHIEF_AGENT_DOC_AUTHORITY_MAP.md (added 4 new docs to Technical Reference, added 3 new workstreams to workstream picture, updated timestamp), DEPLOY_PROTOCOL.md verified current.

This is your final commit.

---

## What is NOT in scope

- **No code changes.** Do not modify any Python, TypeScript, SQL, or configuration file.
- **No production SQL queries.** Do not run live database queries to check row counts. Use the work log.
- **No changes to `docs/DATA_ENGINE_X_ARCHITECTURE.md`.** This is a separate architectural document — the chief agent updates it.
- **No changes to `docs/STRATEGIC_DIRECTIVE.md` or `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`.** Doctrine docs are not updated by executors.
- **No changes to `docs/AUTH_MODEL.md`, `docs/API_SURFACE.md`, `docs/PERSISTENCE_MODEL.md`, `docs/DATA_ACCESS_AND_AUTH_GUIDE.md`, or `docs/GLOBAL_DATA_MODEL_ANALYSIS.md`.** These were produced today and are correct as-is.
- **No changes to individual `docs/EXECUTOR_DIRECTIVE_*.md` files.** They are historical scope documents.
- **No new files created** (except the work log entry which appends to an existing file).
- **No pushing.** Commit locally only.

---

## Commit convention

Each deliverable is one commit. Do not push.

---

## When done

Report back with:

(a) **CLAUDE.md changes:** For each of the 7 sub-edits (1a–1g), confirm it was made. Specifically: how many operations were added to the never-used list, what count was used (old and new), whether Substrate was added, whether the MV broken bullet was removed.

(b) **OPERATIONAL_REALITY_CHECK additions:** Confirm the post-audit section was appended without removing original content. List each subsection added. Confirm the timestamp was updated.

(c) **CHIEF_AGENT_DOC_AUTHORITY_MAP changes:** List each new doc added to Technical Reference. Confirm workstreams were updated. Confirm timestamp updated.

(d) **DEPLOY_PROTOCOL.md:** State whether a change was required or the file was already current.

(e) **Anything to flag:** Any claim in this directive that contradicted the work log, any section you could not update because the source of truth was ambiguous, any stale content you found that was out of scope for this directive (flag it for the chief agent rather than silently fixing it).
