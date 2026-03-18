# Global Data Model Analysis

**Last updated:** 2026-03-18T23:59:00Z

---

## Section 1: Executive Summary

Data-engine-x currently uses an org-scoped entity model: every `company_entities`, `person_entities`, and `job_posting_entities` row is partitioned by `org_id`, and the same real-world company enriched by two different orgs produces two completely independent database records with different entity IDs. The project's own design doctrine (`ENTITY_DATABASE_DESIGN_PRINCIPLES.md`, Principles 3 and 4) states that entities should be global — "a company is a company" — and that each real-world entity should have exactly one record. This analysis evaluates the feasibility, effort, and risk of aligning the production data model with the stated doctrine by removing `org_id` from entity identity resolution and moving to a shared entity layer.

The migration is technically feasible but represents a **large** effort (estimated 25–35 files across Python services, routers, Trigger.dev orchestration, and tests) with **high risk**. The single hardest problem is entity identity resolution: entity IDs are currently deterministic UUID5 hashes that include `org_id` in the seed, meaning the same company domain under two orgs produces two different UUIDs. A global model requires re-hashing all entity IDs, updating every foreign key reference, and handling merge conflicts for any entities that exist under multiple orgs. The biggest product risk is enrichment cost fairness — if Org A pays for a BlitzAPI enrichment and the result becomes globally visible, Org B gets it free.

The recommended path is **Alternative C (Hybrid)**: globalize entity tables while keeping dedicated tables org-scoped, preceded by prerequisite work to fix broken auto-persist paths and migrate remaining pipelines off `run-pipeline.ts`. This aligns with the doctrine, avoids the semantic mismatch of globalizing org-specific analysis tables, and can be sequenced after current reliability work is complete.

---

## Section 2: Doctrinal Position vs. Production Reality

### The Doctrine

`docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` Principle 3 states: *"Entities Are Global, Not Tenant-Scoped. A company is a company. A person is a person. These exist independently of which client requested the data or which tenant triggered the enrichment. Entity tables do not have org_id as a scoping mechanism."*

Principle 4 states: *"One Entity, One Record. Each real-world entity has exactly one record in the entity table. Identity resolution determines which record a data point belongs to. Deduplication prevents the same entity from having multiple records."*

### The Production Reality

The doctrine has **never been followed** for entity tables. From the initial schema (`001_initial_schema.sql`) through the entity state migration (`007_entity_state.sql`) and the schema split (`021_schema_split_ops_entities.sql`), entity tables have always carried `org_id` as a primary key component:

- `company_entities`: PRIMARY KEY (`org_id`, `entity_id`) — **45,679 rows** in production
- `person_entities`: PRIMARY KEY (`org_id`, `entity_id`) — **2,116 rows** in production
- `job_posting_entities`: PRIMARY KEY (`org_id`, `entity_id`) — **1 row** in production
- `entity_timeline`: **4,345 rows**, all with `org_id`
- `entity_snapshots`: **6,407 rows**, all with `org_id`

### Known Duplicates

The three live orgs (Staffing Activation, AlumniGTM, Substrate) have operated on partially overlapping target companies. However, the bulk of entity data comes from Substrate org via Clay ingestion (45,591 of 45,679 company entities). Cross-org duplication is likely minimal at current scale but would grow as more orgs activate.

### Key Gap

The doctrine was written as an aspirational target, not a description of what was built. The `entity_state.py` code computes entity IDs using UUID5 hashes that include `org_id` in the seed string (e.g., `company:{org_id}:domain:{canonical_domain}`), making org-scoping baked into the identity layer — not just a visibility filter.

---

## Section 3: Current Org-Scoping Inventory (Exhaustive)

Based on tracing all 41 migration files in `supabase/migrations/` and cross-referencing with application code:

### Identity Scoping (org_id is part of the unique/conflict key) — 16 tables

| Table | Schema | Conflict Key | Code Write Path | Code Read/Filter Path |
|---|---|---|---|---|
| `company_entities` | entities | PK (`org_id`, `entity_id`) | `entity_state.py:upsert_company_entity()` | `entities_v1.py:list_company_entities()`, `entity_state.py` natural key lookup |
| `person_entities` | entities | PK (`org_id`, `entity_id`) | `entity_state.py:upsert_person_entity()` | `entities_v1.py:list_person_entities()`, `entity_state.py` natural key lookup |
| `job_posting_entities` | entities | PK (`org_id`, `entity_id`) | `entity_state.py:upsert_job_posting_entity()` | `entities_v1.py:list_job_posting_entities()` |
| `icp_job_titles` | entities | UNIQUE (`org_id`, `company_domain`) | `icp_job_titles_service.py:upsert_icp_job_titles()` | `icp_job_titles_service.py:query_icp_job_titles()` |
| `extracted_icp_job_title_details` | entities | UNIQUE (`org_id`, `company_domain`, `title_normalized`) | `icp_job_titles_service.py:upsert_icp_title_details_batch()` | `icp_job_titles_service.py:query_icp_title_details()` |
| `company_intel_briefings` | entities | UNIQUE (`org_id`, `company_domain`, `client_company_name`) | `company_intel_briefings.py:upsert_company_intel_briefing()` | `company_intel_briefings.py:query_company_intel_briefings()` |
| `person_intel_briefings` | entities | UNIQUE (`org_id`, `person_full_name`, `person_current_company_name`, `client_company_name`) | `person_intel_briefings.py:upsert_person_intel_briefing()` | `person_intel_briefings.py:query_person_intel_briefings()` |
| `company_customers` | entities | UNIQUE (`org_id`, `company_domain`, `customer_domain`) WHERE customer_domain IS NOT NULL | `company_customers.py:upsert_company_customers()` | `company_customers.py:query_company_customers()` |
| `gemini_icp_job_titles` | entities | UNIQUE (`org_id`, `company_domain`) | `gemini_icp_job_titles.py:upsert_gemini_icp_job_titles()` | `gemini_icp_job_titles.py:query_gemini_icp_job_titles()` |
| `company_ads` | entities | UNIQUE (`org_id`, `company_domain`, `platform`, `ad_id`) WHERE ad_id IS NOT NULL | `company_ads.py:upsert_company_ads()` | `company_ads.py:query_company_ads()` |
| `salesnav_prospects` | entities | UNIQUE (`org_id`, `source_company_domain`, `linkedin_url`) WHERE linkedin_url IS NOT NULL | `salesnav_prospects.py:upsert_salesnav_prospects()` | `salesnav_prospects.py:query_salesnav_prospects()` |
| `entity_relationships` | entities | UNIQUE (`org_id`, `source_identifier`, `relationship`, `target_identifier`) | `entity_relationships.py:record_entity_relationship()` | `entity_relationships.py:query_entity_relationships()` |
| `enigma_brand_discoveries` | entities | UNIQUE (`org_id`, `enigma_brand_id`, `discovery_prompt`) | `internal.py:internal_upsert_enigma_brand_discoveries()` | — |
| `enigma_location_enrichments` | entities | UNIQUE (`org_id`, `enigma_brand_id`, `enigma_location_id`) | `internal.py:internal_upsert_enigma_location_enrichments()` | — |
| `blueprints` | ops | UNIQUE (`org_id`, `name`) | `submission_flow.py` | batch submit blueprint lookup |
| `company_blueprint_configs` | ops | UNIQUE (`org_id`, `company_id`, `name`) | — | — |

### Visibility Scoping (org_id used for query filtering, NOT part of unique key) — 8 tables

| Table | Schema | Code Write Path | Code Read/Filter Path |
|---|---|---|---|
| `entity_timeline` | entities | `entity_timeline.py:record_entity_event()` | `entities_v1.py:get_entity_timeline()` `.eq("org_id", org_id)` |
| `entity_snapshots` | entities | `entity_state.py:_capture_entity_snapshot()` | `entities_v1.py:get_entity_snapshots()` `.eq("org_id", org_id)` |
| `company_entity_associations` | ops | `internal.py:internal_upsert_entity_state()` | `entities_v1.py` sub-filtering |
| `users` | ops | — | auth lookups |
| `api_tokens` | ops | — | `dependencies.py:get_current_auth()` token lookup |
| `companies` | ops | — | auth resolution, company scoping |
| `lists` | ops | — | — |
| `list_members` | ops | — | — |

### Lineage Tracking (org_id records who initiated, no uniqueness/visibility effect) — 7 tables

| Table | Schema | Code Write Path | Code Read/Filter Path |
|---|---|---|---|
| `submissions` | ops | `submission_flow.py:create_*_submission()` | `execute_v1.py:batch_status()` `.eq("org_id", org_id)` |
| `pipeline_runs` | ops | `submission_flow.py` | `execute_v1.py:batch_status()` `.eq("org_id", org_id)` |
| `step_results` | ops | `submission_flow.py` | `execute_v1.py:batch_status()` `.eq("org_id", org_id)` |
| `operation_runs` | ops | `operation_history.py:persist_operation_execution()` | — |
| `company_blueprint_schedules` | ops | — | — |
| `company_blueprint_schedule_runs` | ops | — | — |
| `orgs` | ops | — (root table) | auth resolution |

**Note:** `submissions`, `pipeline_runs`, and `step_results` are classified as lineage tracking because `org_id` records which tenant initiated the execution. However, `batch_status` queries do filter by `org_id` for tenant isolation, so they also serve a visibility-scoping function. The classification reflects primary purpose.

### Summary

| Classification | Count |
|---|---|
| Identity scoping | 16 |
| Visibility scoping | 8 |
| Lineage tracking | 7 |
| **Total org-scoped tables** | **31** |

---

## Section 4: What Already Works as Global Data

### Tables Without org_id — 22 tables + 1 materialized view

**FMCSA Tables (18):** `motor_carrier_census_records`, `carrier_registrations`, `operating_authority_histories`, `operating_authority_revocations`, `insurance_policies`, `insurance_policy_filings`, `insurance_policy_history_events`, `carrier_safety_basic_measures`, `carrier_safety_basic_percentiles`, `carrier_inspection_violations`, `carrier_inspections`, `commercial_vehicle_crashes`, `vehicle_inspection_units`, `vehicle_inspection_special_studies`, `vehicle_inspection_citations`, `out_of_service_orders`, `process_agent_filings`, `insurance_filing_rejections`

All use UNIQUE (`feed_date`, `source_feed_name`, `row_position`) or `record_fingerprint` as dedup keys. No org_id column exists.

**Federal Data Tables (3):** `sam_gov_entities` (867,137 rows), `usaspending_contracts` (14,665,610 rows), `sba_7a_loans` (356,375 rows)

**Signal Table (1):** `fmcsa_carrier_signals` — UNIQUE (`signal_type`, `feed_date`, `entity_key`)

**Materialized View (1):** `mv_federal_contract_leads` (1,340,862 rows)

### Patterns That Make Global Data Work

1. **Auth:** FMCSA and federal endpoints use `_resolve_flexible_auth` which accepts any auth type (tenant JWT, API token, super-admin, internal service). No org_id is extracted or required.

2. **Queries:** No `.eq("org_id", ...)` filter. All authenticated users see the same data. Filtering is by business attributes (state, DOT number, NAICS code, etc.).

3. **Writes:** FMCSA data is ingested via Trigger.dev tasks calling internal endpoints that use `require_internal_key` only (no `require_internal_context`, no org header). Federal data uses similar internal ingestion endpoints.

4. **Schema:** Global tables live in the `entities` schema alongside org-scoped entity tables. The separation is logical (no org_id column) not physical (different schema).

5. **Endpoint pattern example** — `app/routers/fmcsa_v1.py`:
   - `query_fmcsa_carriers_endpoint()` calls `query_fmcsa_carriers(filters, limit, offset)` — no org_id
   - `get_fmcsa_carrier_detail_endpoint()` calls `get_fmcsa_carrier_detail(dot_number)` — joins 6 tables, no org filter on any
   - Service functions in `fmcsa_carrier_query.py` and `fmcsa_carrier_detail.py` query `entities.*` tables directly without any tenant scoping

---

## Section 5: Entity Tables — What Would Change

### 5a. Current Identity Resolution Logic

**Company Entities** (`entity_state.py:upsert_company_entity()`):

1. If explicit `entity_id` parameter provided → use as-is
2. Natural key lookup: query `company_entities` with `.eq("org_id", org_id).eq("canonical_domain", canonical_domain)` — **org_id participates in lookup**
3. If no match by domain, try LinkedIn URL: `.eq("org_id", org_id).eq("linkedin_url", linkedin_url)`
4. If no match → generate deterministic UUID5 from seed `company:{org_id}:domain:{canonical_domain}` (or LinkedIn/name fallbacks) — **org_id is baked into the entity ID itself**

**Person Entities** (`entity_state.py:upsert_person_entity()`):

1. If explicit `entity_id` → use as-is
2. Natural key lookup: `.eq("org_id", org_id).eq("linkedin_url", linkedin_url)` then `.eq("org_id", org_id).eq("work_email", work_email)` — **org_id participates**
3. If no match → UUID5 from `person:{org_id}:linkedin:{linkedin_url}` — **org_id in seed**

**Job Posting Entities** (`entity_state.py:upsert_job_posting_entity()`):

1. If explicit `entity_id` → use as-is
2. Natural key lookup: `.eq("org_id", org_id).eq("theirstack_job_id", theirstack_job_id)` — **org_id participates**
3. If no match → UUID5 from `job:{org_id}:theirstack:{theirstack_job_id}` — **org_id in seed**

**Critical finding:** `org_id` participates in identity resolution at three levels: (1) natural key database lookup, (2) deterministic UUID5 generation, and (3) the primary key itself (`org_id`, `entity_id`). All three must change for globalization.

### 5b. What Happens If org_id Is Removed

**Upsert conflicts:** Yes. If Org A and Org B both enrich `example.com`, removing org_id means they'd resolve to the same entity. Org B's enrichment would trigger an optimistic-locking update against Org A's existing record.

**Canonical payload:** The current merge strategy is `_merge_non_null()` — incoming non-null values overwrite existing values per field. In a global model, Org B's enrichment would overwrite Org A's values for any overlapping fields. This is **last-write-wins per field**, which means the most recent enrichment from any org determines the canonical value.

**Record version / optimistic locking:** Currently, each org's entity has its own version counter. In a global model, the version counter is shared. If Org A is at version 5 and Org B tries to update expecting version 4, the update fails with `EntityStateVersionError`. Cross-org upsert races would cause legitimate failures.

**Source providers:** The `_merge_str_lists()` function does union-merge (deduplicated, order-preserving). In a global model, the `source_providers` array would accumulate providers from all orgs — this is actually the desired behavior.

**Metadata fields:** `last_enriched_at`, `last_operation_id`, `last_run_id` would reflect whichever org enriched most recently, regardless of org. There is **no enrichment provenance** — you cannot tell which org contributed which data to a global entity.

### 5c. Every Code Path That Filters Entity Tables by org_id

**Query endpoints (`entities_v1.py`):**
- `list_company_entities()` — `.eq("org_id", auth.org_id)`
- `list_person_entities()` — `.eq("org_id", auth.org_id)`
- `list_job_posting_entities()` — `.eq("org_id", org_id)` (from flexible auth)
- `get_entity_timeline()` — `.eq("org_id", org_id)`
- `get_entity_snapshots()` — `.eq("org_id", org_id)`
- `entity_ingest()` — org_id from payload or auth

**Internal endpoints (`internal.py`):**
- `internal_upsert_entity_state()` — extracts org_id from `pipeline_runs` row, passes to upsert
- `internal_check_entity_state_freshness()` — org_id from `require_internal_context`
- `internal_record_step_timeline_event()` — org_id from payload

**Entity state services (`entity_state.py`):**
- `upsert_company_entity()` — natural key lookup `.eq("org_id", org_id)`, update `.eq("org_id", org_id)`, insert with `org_id`
- `upsert_person_entity()` — same pattern
- `upsert_job_posting_entity()` — same pattern
- `_capture_entity_snapshot()` — writes org_id to entity_snapshots
- UUID5 generation functions — org_id in hash seed

**Entity timeline (`entity_timeline.py`):**
- `record_entity_event()` — writes org_id to entity_timeline

**Trigger.dev (`run-pipeline.ts`):**
- `callExecuteV1()` — sets `x-internal-org-id` header
- `callEntityStateFreshnessCheck()` — sets `x-internal-org-id` header
- `emitStepTimelineEvent()` — passes org_id in request body
- All entity state persist calls pass org_id via headers or body

**Trigger.dev (`internal-api.ts`):**
- `InternalApiClient.post()` — sets `x-internal-org-id: this.authContext.orgId` on every request

---

## Section 6: Dedicated Tables — What Would Change

### Table-by-Table Analysis

| Table | Conflict Key | org_id in Key? | Globalizable? | Reasoning |
|---|---|---|---|---|
| `icp_job_titles` | (`org_id`, `company_domain`) | Yes | **No** | ICP titles are org-specific — each org targets different buyer personas for the same company |
| `extracted_icp_job_title_details` | (`org_id`, `company_domain`, `title_normalized`) | Yes | **No** | Derived from ICP analysis, inherently org-specific |
| `gemini_icp_job_titles` | (`org_id`, `company_domain`) | Yes | **No** | Same as icp_job_titles — Gemini variant of org-specific ICP analysis |
| `company_intel_briefings` | (`org_id`, `company_domain`, `client_company_name`) | Yes | **No** | Briefings are scoped to `client_company_name` — the analysis is about how Company X relates to YOUR business |
| `person_intel_briefings` | (`org_id`, `person_full_name`, `person_current_company_name`, `client_company_name`) | Yes | **No** | Same — person analysis in context of client's business |
| `company_customers` | (`org_id`, `company_domain`, `customer_domain`) | Yes | **Maybe** | Customer relationships are objective facts about the world, but discovery depends on source context and may differ by provider/prompt |
| `company_ads` | (`org_id`, `company_domain`, `platform`, `ad_id`) | Yes | **Yes** | Ads are objective public data — an ad exists regardless of which org discovered it |
| `salesnav_prospects` | (`org_id`, `source_company_domain`, `linkedin_url`) | Yes | **No** | Prospects are discovered via org-specific Sales Nav search URLs with client-specific templates |
| `entity_relationships` | (`org_id`, `source_identifier`, `relationship`, `target_identifier`) | Yes | **Maybe** | `person → works_at → company` relationships are objective facts. But relationship discovery is org-initiated |
| `enigma_brand_discoveries` | (`org_id`, `enigma_brand_id`, `discovery_prompt`) | Yes | **Maybe** | Brand-level data is objective, but discoveries are prompt-scoped |
| `enigma_location_enrichments` | (`org_id`, `enigma_brand_id`, `enigma_location_id`) | Yes | **Yes** | Location enrichment data is objective — revenue, employee counts, attributes are facts |

### Key Insight

Dedicated tables fall into two categories:

**Inherently org-specific (6 tables):** ICP job titles (both variants), extracted title details, company/person intel briefings, salesnav prospects. These represent analysis results that depend on the requesting org's business context (their ICP definition, their target buyer personas, their Sales Nav templates). Globalizing these would lose the semantic distinction between "ICP titles for Org A's sales motion" and "ICP titles for Org B's different sales motion."

**Candidates for globalization (5 tables):** Company customers (objective facts, with caveats), company ads (public data), entity relationships (objective facts), enigma brand discoveries (with prompt-scoping caveat), enigma location enrichments (objective data). These represent facts about the world rather than org-specific analysis.

---

## Section 7: Execution Lineage — What Stays Org-Scoped

### Execution Lineage Tables

| Table | Schema | org_id Usage | References Entity Data? |
|---|---|---|---|
| `submissions` | ops | Written on creation, filtered on status queries | No direct entity reference |
| `pipeline_runs` | ops | Written on creation, used to extract org_id for entity upserts | Contains `submission_id` FK |
| `step_results` | ops | Written on creation | Contains `output_payload` (entity data in JSON) |
| `operation_runs` | ops | Written from auth context | Contains `operation_id`, `input_payload`, `output_payload` |
| `operation_attempts` | ops | None (references `run_id` FK) | Contains raw provider responses |

### Why They Must Stay Org-Scoped

1. **Audit:** Each org needs to know what operations they ran, when, and what results they got
2. **Billing:** Provider API calls are org-attributable costs; execution lineage is the billing source of truth
3. **Access control:** Org A should not see Org B's pipeline runs, step results, or operation history
4. **Privacy:** Operation inputs may contain org-specific context (target lists, ICP definitions, client company details)

### Join Pattern Changes

Currently, entity upserts extract `org_id` from the `pipeline_runs` row (`internal.py:internal_upsert_entity_state()`). In a global model:
- Pipeline runs keep `org_id` (lineage stays org-scoped)
- Entity upserts would still read `org_id` from the run for lineage purposes, but would NOT use it for entity identity resolution
- The entity_id written to the global entity table would not be org-scoped
- `company_entity_associations` (which links entities to companies within orgs) would become the primary mechanism for "which entities belong to this org's workspace" — this table already exists and supports this pattern

---

## Section 8: Identity Resolution Conflicts

### Current Merge Strategy

`upsert_company_entity()` uses a **last-write-wins per field** strategy via `_merge_non_null()`:

```
merged_payload = _merge_non_null(existing_payload, incoming_fields)
```

Non-null incoming values overwrite existing values. Null incoming values preserve existing values. This means later enrichments accumulate data without destroying earlier fields — unless they provide a different value for the same field.

### Record Version / Optimistic Locking

The upsert reads the existing `record_version`, computes `next_version = existing_version + 1`, then updates with `.eq("record_version", existing_version)`. If another write incremented the version between read and write, the update matches 0 rows and raises `EntityStateVersionError`.

In a global model, this means:
- Two orgs enriching the same entity simultaneously → one fails with version error
- The failed org would need retry logic (which does not currently exist in the entity upsert path)
- At current scale (3 orgs, low enrichment volume), this is unlikely but not impossible

### Source Providers

`source_providers` is a string array that uses union-merge (`_merge_str_lists`). In a global model, this array would accumulate all providers used by all orgs — e.g., `["blitzapi", "prospeo", "clay"]`. This is actually desirable: it shows the full provenance of enrichment sources.

### Enrichment Provenance

There is **no per-field provenance tracking**. You cannot determine:
- Which org contributed which field value
- When each field was last updated (only `last_enriched_at` at the entity level)
- Which provider produced which field value

The `entity_timeline` table provides event-level provenance (which org ran which operation), but does not track field-level attribution. The `entity_snapshots` table preserves pre-update state but does not annotate which org triggered the snapshot.

### Proposed Merge Strategies

**Strategy A: Last Write Wins (current behavior, extended to cross-org)**
- Pro: Zero code change to merge logic; works today
- Con: Later enrichment overwrites earlier; no way to prefer higher-quality data over lower-quality; enrichment cost fairness problem
- Complexity: Minimal

**Strategy B: Most Recent Enrichment Per Field**
- Requires: New `field_timestamps` JSONB column tracking per-field update timestamps
- Pro: Preserves best available data per field; later enrichments only overwrite if they have data
- Con: Significant schema change; merge logic complexity increases; query performance impact for large payloads
- Complexity: Medium-High

**Strategy C: Append-Only Enrichment Log**
- Requires: New `enrichment_contributions` table with `(entity_id, org_id, operation_id, fields_contributed, contributed_at)`
- Pro: Full provenance; reversible; supports billing attribution
- Con: Query complexity increases (must join/merge contributions); storage grows linearly with enrichment volume
- Complexity: High

**Strategy D: Source Confidence Scoring**
- Requires: Provider reliability weights, field-level confidence scores, conflict resolution rules
- Pro: Best possible data quality
- Con: Extreme complexity; subjective weight assignment; maintenance burden
- Complexity: Very High

**Recommendation:** Strategy A (last write wins) is sufficient at current scale. Strategy C (enrichment log) should be considered if billing attribution becomes a product requirement.

---

## Section 9: Auth and API Surface Changes

### Entity Query Endpoints

| Endpoint | Current Auth | Current org_id Filter | Change Needed |
|---|---|---|---|
| `GET /api/v1/entities/companies` | `get_current_auth` (tenant only) | `.eq("org_id", auth.org_id)` | Remove org_id filter OR make optional; add `_resolve_flexible_auth`; use `company_entity_associations` for workspace scoping |
| `GET /api/v1/entities/persons` | `get_current_auth` (tenant only) | `.eq("org_id", auth.org_id)` | Same as above |
| `GET /api/v1/entities/job-postings` | `_resolve_flexible_auth` | `.eq("org_id", org_id)` | Remove org_id filter; super-admin sees all |
| `GET /api/v1/entities/timeline` | `_resolve_flexible_auth` | `.eq("org_id", org_id)` | Keep org_id filter (timeline is org-scoped lineage) |
| `GET /api/v1/entities/snapshots` | `_resolve_flexible_auth` | `.eq("org_id", org_id)` | Keep org_id filter (snapshots are org-scoped) |

### Dedicated Table Query Endpoints

All dedicated table query endpoints use `_resolve_flexible_auth` and pass `org_id` to their service query functions. For tables that stay org-scoped (ICP titles, briefings, salesnav), no change needed. For tables that globalize (company_ads, entity_relationships, enigma_location_enrichments), the org_id filter would be removed.

### Internal Upsert Endpoints

| Endpoint | Current org_id Source | Change Needed |
|---|---|---|
| `POST /api/internal/entity-state/upsert` | Extracted from `pipeline_runs.org_id` | Remove org_id from entity identity resolution; still read org_id for lineage/timeline |
| `POST /api/internal/entity-state/freshness` | `x-internal-org-id` header | Remove org_id from freshness lookup key |
| Dedicated table upserts (ICP, briefings, etc.) | `x-internal-org-id` header | No change for org-scoped tables; remove org_id from conflict key for globalized tables |

### Batch Submit and Status

- `batch_submit`: org_id stays (submission is org-scoped lineage)
- `batch_status`: org_id filter on submissions/pipeline_runs stays; entity data returned from step_results would reference global entity IDs

### Company Entity Associations

`company_entity_associations` (UNIQUE `org_id`, `company_id`, `entity_type`, `entity_id`) is the existing mechanism for "which entities are relevant to this company's workspace." In a global model, this becomes the **primary tenant-scoping mechanism** for entity visibility:
- When an org enriches a global entity, an association is recorded
- Entity query endpoints filter through associations instead of direct org_id on entity tables
- This table already exists and is written during entity upserts in `internal.py`

### Super-Admin Auth

Currently, super-admin must provide `org_id` for entity queries. In a global model, super-admin would see all entities without org scoping (like FMCSA data today). The `_resolve_flexible_auth` pattern already supports this — super-admin endpoints for FMCSA data work without org_id.

---

## Section 10: Migration Path

### Phase 1: Schema Changes

1. **Drop org_id from entity table primary keys:**
   - `company_entities`: PK changes from (`org_id`, `entity_id`) to (`entity_id`)
   - `person_entities`: PK changes from (`org_id`, `entity_id`) to (`entity_id`)
   - `job_posting_entities`: PK changes from (`org_id`, `entity_id`) to (`entity_id`)
   - `org_id` column becomes nullable or is retained for lineage (records which org created the entity)

2. **Add natural key unique indexes (without org_id):**
   - `company_entities`: UNIQUE (`canonical_domain`) WHERE `canonical_domain` IS NOT NULL
   - `company_entities`: UNIQUE (`linkedin_url`) WHERE `linkedin_url` IS NOT NULL
   - `person_entities`: UNIQUE (`linkedin_url`) WHERE `linkedin_url` IS NOT NULL
   - `person_entities`: UNIQUE (`work_email`) WHERE `work_email` IS NOT NULL
   - `job_posting_entities`: UNIQUE (`theirstack_job_id`) WHERE `theirstack_job_id` IS NOT NULL

3. **Globalized dedicated tables:** Same pattern — remove org_id from conflict key for company_ads, entity_relationships, enigma tables.

4. **entity_timeline and entity_snapshots:** Keep org_id column (lineage). Remove any index that includes org_id as a uniqueness component.

### Phase 2: Data Migration

**Entity deduplication scale estimate:**
- 45,679 company entities across 3 orgs
- Bulk (45,591) from Substrate via Clay ingestion — likely minimal cross-org overlap
- Remaining ~88 entities from AlumniGTM and Staffing Activation may overlap with Clay-ingested Substrate entities
- Estimated merge conflicts: **low** (likely <100 entities with cross-org duplicates at current scale)

**Merge process:**
1. Identify duplicate natural keys across orgs: `SELECT canonical_domain, COUNT(DISTINCT org_id) FROM company_entities GROUP BY canonical_domain HAVING COUNT(DISTINCT org_id) > 1`
2. For each duplicate set: pick the most recently enriched record as the survivor, merge `canonical_payload` using `_merge_non_null`, union-merge `source_providers`
3. Re-compute entity_id as UUID5 without org_id: `company:domain:{canonical_domain}` (new seed format)
4. Update all FK references: `entity_timeline.entity_id`, `entity_snapshots.entity_id`, `company_entity_associations.entity_id`, dedicated table `company_entity_id` columns
5. Delete merged duplicate rows

**Estimated complexity:** Medium. The actual data volume is manageable, but FK reference updates touch many tables.

### Phase 3: Code Changes

| Category | Estimated Files | Key Changes |
|---|---|---|
| Entity state services | 1 (`entity_state.py`) | Remove org_id from natural key lookups, UUID5 seeds, update/insert operations |
| Entity timeline | 1 (`entity_timeline.py`) | Keep org_id as lineage parameter, not identity |
| Entity query router | 1 (`entities_v1.py`) | Replace org_id entity filters with association-based filtering |
| Internal router | 1 (`internal.py`) | Update entity upsert to not use org_id for identity; update freshness check |
| Dedicated table services (globalized only) | 3-5 (company_ads, entity_relationships, enigma services) | Remove org_id from conflict keys and queries |
| Dedicated table services (staying org-scoped) | 0 | No change |
| Execute router | 1 (`execute_v1.py`) | Minor — batch status entity data references |
| Auth dependencies | 0 | No change needed |
| Trigger.dev run-pipeline | 1 (`run-pipeline.ts`) | Update entity upsert calls (org_id becomes optional/lineage-only) |
| Trigger.dev internal-api | 1 (`internal-api.ts`) | org_id header still sent for lineage |
| Trigger.dev dedicated workflows | 3-5 (workflows that do entity upserts) | Update entity upsert calls |
| Tests | 5-10 | Update test fixtures, mock data, assertions |
| **Total** | **~25-35 files** | — |

### Phase 4: API Contract Changes

- Entity query response shape: `org_id` field would either be removed or become the "created_by_org_id"
- Entity ID values change (UUID5 re-hash without org_id) — this is a **breaking change** for any integration that stores entity IDs
- Dedicated table query responses for globalized tables lose org_id filtering
- Batch status response: entity data referenced by step_results uses new entity IDs

**Overall scope:** Large effort, high risk. Estimated 25-35 files, 2-4 weeks of focused work including testing.

---

## Section 11: Risks and Tradeoffs

### 1. Data Ownership Ambiguity

Who "owns" a global entity? If Org A enriched `example.com` via BlitzAPI (costing API credits), and Org B queries the same entity and gets BlitzAPI data for free, there's a fairness problem. The current model avoids this by keeping enrichments siloed.

**Mitigation:** Track enrichment contributions per org (Strategy C from Section 8). Charge orgs only for enrichments they initiate, not for inherited data.

### 2. Privacy Implications

In a global model, Org A can see that `example.com` was enriched (because the entity exists with populated fields). They cannot directly see that Org B enriched it, but the presence of enrichment data from providers Org A didn't use would be inferrable.

**Mitigation:** If privacy is required, the shared-reference-plus-overlay model (Alternative A) separates org-specific enrichment from global identity.

### 3. Rollback Difficulty

Once entity IDs are re-hashed and duplicate records are merged, the operation is **practically irreversible**. The old org-scoped entity IDs would no longer exist, and any external system referencing them would break.

**Mitigation:** Full database backup before migration. Keep a mapping table (`old_org_id + old_entity_id → new_entity_id`) permanently.

### 4. Clay-Ingested Data Impact

45,591 company entities ingested under Substrate org become globally visible. This is likely desired (the data represents objective company facts), but should be confirmed by the project owner.

### 5. Enrichment Cost Fairness

The most significant product risk. Provider API calls cost money. In a global model, one org's enrichment benefits all orgs. Options: (a) accept this as a feature ("shared intelligence pool"), (b) track per-org enrichment contributions and expose in billing, (c) keep enrichments org-scoped via overlay model.

### 6. Migration Complexity for Existing Data

At current scale (45,679 companies, 2,116 persons), the data migration is manageable. The complexity is in FK reference updates across entity_timeline (4,345 rows), entity_snapshots (6,407 rows), company_entity_associations, and dedicated tables.

### 7. Concurrent Enrichment Races

In a global model, two orgs enriching the same entity simultaneously hit the optimistic lock. One fails with `EntityStateVersionError`. The system does not currently retry entity upserts on version conflict.

**Mitigation:** Add retry-on-version-conflict logic to entity upsert. At current scale (3 orgs, low concurrent enrichment), this is low probability.

### 8. Dedicated Table Semantic Mismatch

ICP job titles, intel briefings, and salesnav prospects are inherently org-specific — they represent org-contextual analysis, not world facts. Globalizing these would merge analysis that should stay separate (Org A's ICP is different from Org B's ICP for the same target company).

**Mitigation:** Hybrid approach (Alternative C) — globalize entities, keep dedicated tables org-scoped.

---

## Section 12: Alternative Approaches

### Alternative A: Shared Reference Layer + Org-Scoped Enrichment Overlay

**Model:** Global entity records contain only identity fields (domain, LinkedIn URL, name). Each org's enrichment results are stored in an org-scoped `entity_enrichments` overlay table that references the global entity. Queries merge global identity with org-specific enrichment.

| Dimension | Assessment |
|---|---|
| Changes vs. current | New global identity table; existing entity tables become overlay; complex join queries |
| Changes vs. full globalization | More tables, more complex queries, but preserves per-org enrichment privacy |
| Implementation complexity | **Very High** — new table, new merge-on-read logic, all query endpoints change |
| Data model cleanliness | Clean separation of identity vs. enrichment, but adds query complexity |
| Follows doctrine? | Partially — entities are global, but enrichment is org-scoped |

### Alternative B: Copy-on-Read with Global Source of Truth

**Model:** A single global entity record is the source of truth. All orgs read the same record. Enrichments update the global record (all orgs benefit). Execution lineage stays org-scoped.

| Dimension | Assessment |
|---|---|
| Changes vs. current | Remove org_id from entity identity; all enrichments accumulate on one record |
| Changes vs. full globalization | This IS full globalization for entity tables |
| Implementation complexity | **High** — same as Section 10 migration path |
| Data model cleanliness | Clean — one entity, one record |
| Follows doctrine? | **Yes** — fully aligns with Principles 3 and 4 |

### Alternative C: Hybrid — Global Entities, Org-Scoped Dedicated Tables

**Model:** Entity tables (`company_entities`, `person_entities`, `job_posting_entities`) go global. Dedicated tables (`icp_job_titles`, `company_intel_briefings`, `person_intel_briefings`, `gemini_icp_job_titles`, `salesnav_prospects`) stay org-scoped because they represent org-specific analysis. Objective-fact dedicated tables (`company_ads`, `entity_relationships`, `enigma_location_enrichments`) optionally globalize.

| Dimension | Assessment |
|---|---|
| Changes vs. current | Entity identity resolution removes org_id; dedicated table identity unchanged for org-specific tables |
| Changes vs. full globalization | Smaller scope — ~6 fewer tables to migrate; avoids semantic mismatch |
| Implementation complexity | **High** (entity tables) but avoids dedicated table semantic problems |
| Data model cleanliness | Best of both worlds — global facts as global records, org-specific analysis as org-scoped |
| Follows doctrine? | **Yes** for entities (Principles 3 and 4); pragmatic exception for org-specific analysis tables |

**This is the recommended approach.**

---

## Section 13: Recommendation

**Recommendation: Proceed with Alternative C (Hybrid), deferred until prerequisites are met.**

### Rationale

1. **Doctrinal alignment:** Alternative C brings entity tables into compliance with Principles 3 and 4 while pragmatically keeping org-specific analysis tables scoped correctly.

2. **Semantic correctness:** ICP job titles, intel briefings, and salesnav prospects are genuinely org-specific — globalizing them would create data quality problems. Company entities and person entities are world facts that should be global.

3. **Manageable scope at current scale:** With only 3 active orgs and minimal cross-org entity overlap, the data migration is tractable. The code change scope (~25-35 files) is significant but well-defined.

4. **Existing infrastructure supports it:** `company_entity_associations` already provides the org-to-entity mapping needed for workspace-scoped visibility. FMCSA/federal data already demonstrates the global-data query pattern.

### Prerequisites (must be completed first)

1. **Fix broken auto-persist paths** — company_customers, gemini_icp_job_titles, salesnav_prospects, company_ads all have 0 production rows. These must work before touching the data model.

2. **Complete run-pipeline.ts migration** — The legacy pipeline runner handles entity upserts differently from dedicated workflows. Migrating all pipelines to dedicated workflows (which use `InternalApiClient` with consistent header patterns) simplifies the global migration.

3. **Add retry-on-version-conflict** — Entity upserts currently fail on version conflict with no retry. In a global model, cross-org version conflicts become more likely.

4. **Enrichment provenance tracking** — Before merging entity records across orgs, implement at minimum an `enrichment_contributions` log (Strategy C from Section 8) to support future billing attribution.

### Sequencing

1. Fix auto-persist (current workstream)
2. Complete dedicated workflow migration (current workstream)
3. Add version-conflict retry + enrichment provenance tracking (new work)
4. Schema migration: global entity tables + data dedup/merge
5. Code migration: entity_state.py, routers, Trigger.dev
6. Optional Phase 2: Globalize objective-fact dedicated tables (company_ads, entity_relationships, enigma)

### Risk Level

**High.** Entity ID re-hashing is irreversible and touches the core identity layer. The migration must be executed with full backup, a mapping table for old→new entity IDs, and thorough testing in staging before production. The product question of enrichment cost fairness should be resolved at the business level before engineering begins.
