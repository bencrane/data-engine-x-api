# Executor Directive: Global Data Model Analysis

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The entity data model in data-engine-x is currently org-scoped — each org has its own copy of `company_entities`, `person_entities`, dedicated tables, etc. This means if Org A enriches example.com and Org B enriches example.com, two separate entity records exist. Meanwhile, FMCSA and federal data tables are already global — any authenticated user sees the same data regardless of org. The project owner is evaluating whether to move enrichment data (entity tables, dedicated tables) to a global model where enrichment results are shared across orgs rather than siloed. This directive scopes an exhaustive analysis document that informs that decision with full technical grounding.

**This is a documentation-only directive.** No code changes. No refactoring. No migrations. The deliverable is a comprehensive analysis report grounded in actual code tracing, not inference from docs.

**Critical read-first:**
- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — the authoritative reference for current data visibility, auth scoping, and table-level org-scoping inventory. This is the baseline the analysis compares against.
- `docs/PERSISTENCE_MODEL.md` — every persistence path, what writes `org_id`, where `org_id` is used as a scoping key, how entity upserts work, the confirmed-write vs. auto-persist distinction.
- `docs/AUTH_MODEL.md` — the four auth paths and multi-tenancy model.
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — doctrine. Pay particular attention to Principle 3 ("Entities Are Global, Not Tenant-Scoped") and Principle 4 ("One Entity, One Record"). Note that the current production implementation does NOT follow these principles — entities are org-scoped and duplicated per org. This directive's analysis document should explicitly address the gap between the stated doctrine and the production reality.

---

## Existing code to read

Before writing any analysis, read and trace these files. Do not rely on docs alone — the analysis must cite actual code paths.

### Auth and scoping

- `app/auth/dependencies.py` — `get_current_auth()`, how `org_id` is resolved for each auth type, the internal auth path that injects `org_id` from headers
- `app/auth/super_admin.py` — `get_current_super_admin()`, what context it produces (no `org_id`)
- `app/auth/tokens.py` — JWT claims including `org_id`

### Entity state and identity resolution

- `app/services/entity_state.py` — `upsert_company_entity()`, `upsert_person_entity()`, `upsert_job_posting_entity()`. Trace the natural key resolution logic. Note how `org_id` participates in the identity lookup. This is the most important file for understanding what would break in a global model.

### Entity query endpoints

- `app/routers/entities_v1.py` — all entity query endpoints. Trace every `.eq("org_id", ...)` filter. Note the company-scoped sub-filtering via `company_entity_associations`. Note which endpoints use `get_current_auth` vs. `_resolve_flexible_auth`.

### Execution and pipeline orchestration

- `app/routers/execute_v1.py` — how `org_id` flows into `persist_operation_execution()`, batch submit, and status queries. Trace the auth context construction for super-admin.
- `app/services/operation_history.py` — `persist_operation_execution()`, the `org_id` column write.
- `app/services/submission_flow.py` — how `org_id` is written to submissions, pipeline_runs, step_results.

### Dedicated table services

- `app/services/company_customers.py` — `upsert_company_customers()`, note `org_id` in conflict key
- `app/services/icp_job_titles_service.py` — `upsert_icp_job_titles()`, note `org_id` in conflict key
- `app/services/company_intel_briefings.py` — note `org_id` usage
- `app/services/person_intel_briefings.py` — note `org_id` usage
- `app/services/gemini_icp_job_titles.py` — note `org_id` usage
- `app/services/company_ads.py` — note `org_id` usage
- `app/services/salesnav_prospects.py` — note `org_id` usage
- `app/services/entity_relationships.py` — note `org_id` usage
- `app/services/entity_timeline.py` — note `org_id` usage

### Dedicated table query endpoints

- `app/routers/entities_v1.py` — dedicated table query endpoints (icp-job-titles, company-customers, company-ads, etc.). Trace the org_id filtering on each.

### Internal endpoints

- `app/routers/internal.py` — all internal endpoints that accept `org_id` in request body or headers. Pay attention to entity state upsert, dedicated table upserts, and entity timeline recording.

### Global data patterns (the model to study)

- `app/routers/fmcsa_v1.py` — how FMCSA query endpoints work without org scoping. Study the auth pattern (`_resolve_flexible_auth` accepting any auth type), the query pattern (no `org_id` filter), and the write pattern (internal endpoints without org context).
- `app/services/fmcsa_carrier_query.py` — carrier query with no org filter
- `app/services/fmcsa_carrier_detail.py` — multi-table carrier detail with no org filter

### Trigger.dev orchestration

- `trigger/src/tasks/run-pipeline.ts` — how `org_id` flows from payload through the pipeline. Trace how it's passed to internal API calls.
- `trigger/src/workflows/internal-api.ts` — `InternalApiClient`, how `x-internal-org-id` header is set on every request.

### Schema definitions

- `supabase/migrations/001_initial_schema.sql` — original schema including `org_id` columns
- `supabase/migrations/007_entity_state.sql` — entity tables schema
- `supabase/migrations/021_schema_split_ops_entities.sql` — schema split migration
- Any other migrations that create tables with `org_id` columns — scan all migrations to build the complete inventory.

### Reference documents (do not treat as ground truth — verify against code)

- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — Section 7 has a complete table scoping inventory, but verify each claim against actual schema.
- `docs/PERSISTENCE_MODEL.md` — Section 10 has a table-level persistence reference.
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — Principles 3 and 4 define the doctrinal position on global entities.

---

## Deliverable 1: Analysis Document

Create `docs/GLOBAL_DATA_MODEL_ANALYSIS.md`.

The document must include the following sections, in this order. Each section has explicit requirements below. The executor should use judgment on depth and formatting within each section, but the section list and coverage requirements are mandatory.

### Section 1: Executive Summary

2-3 paragraphs. State the question being analyzed, the current model, the proposed model, and the top-level finding (is this feasible, roughly how large is the effort, what's the biggest risk). This section should be readable by someone who doesn't read the rest of the document.

### Section 2: Doctrinal Position vs. Production Reality

`docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` Principle 3 says: "Entities Are Global, Not Tenant-Scoped. A company is a company. A person is a person. These exist independently of which client requested the data or which tenant triggered the enrichment." Principle 4 says: "One Entity, One Record."

Document the gap between this doctrine and the current production state. Specifically:
- How many entity records exist today that are org-scoped? (Use production row counts from `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`: 45,679 company entities, 2,116 persons, 1 job posting, etc.)
- Are there known duplicates? (Multiple orgs enriching the same company domain would produce duplicate records.)
- Has the doctrine ever been followed for entity tables, or has org-scoping been the model since day one?

### Section 3: Current Org-Scoping Inventory (Exhaustive)

For **every table** in the database that has an `org_id` column, document:

| Table | Schema | `org_id` Usage | Conflict Key Includes `org_id`? | Code Paths That Write `org_id` | Code Paths That Filter by `org_id` |
|---|---|---|---|---|---|

This must be exhaustive. Trace the actual migrations (all files in `supabase/migrations/`) and actual code. Do not rely on docs alone — `DATA_ACCESS_AND_AUTH_GUIDE.md` Section 7 is a starting point but verify against schema definitions.

For each table, classify the `org_id` usage into one of:
- **Identity scoping** — `org_id` is part of the unique/conflict key. Removing it changes what constitutes a unique record.
- **Visibility scoping** — `org_id` is used for query filtering (tenants see only their data) but is NOT part of the unique key.
- **Lineage tracking** — `org_id` records who initiated the action but doesn't affect uniqueness or visibility.

This classification is critical because identity-scoping tables are the hardest to migrate to global.

### Section 4: What Already Works as Global Data

Document every table that has NO `org_id` column. For each, document:
- How it's written (ingestion path, auth context)
- How it's queried (which endpoints, what auth types, what filtering)
- How it coexists with org-scoped tables in the same schema

Identify the **patterns** that make global data work today:
- Auth: `_resolve_flexible_auth` accepting any auth type
- Queries: no org_id filter, data visible to all authenticated users
- Writes: internal service auth without org context, or ingestion tasks
- Schema: separate from org-scoped tables conceptually, but in the same `entities` schema

### Section 5: Entity Tables — What Would Change

For each of the three entity tables (`company_entities`, `person_entities`, `job_posting_entities`), document:

**5a. Current identity resolution logic.** Trace `upsert_company_entity()` in `entity_state.py`. Document the natural key lookup. The natural key for companies is `canonical_domain` or `company_linkedin_url` — but is `org_id` part of the lookup? Trace the actual code. Same for persons (natural key is `linkedin_url` or `work_email`) and job postings (`theirstack_job_id`).

**5b. What happens if `org_id` is removed from the identity lookup.** Today, Org A's record for `example.com` and Org B's record for `example.com` are separate rows. If `org_id` is removed from the lookup:
- Would upserts conflict? Would Org B's enrichment overwrite Org A's data?
- What happens to `canonical_payload` — which org's enrichment "wins"?
- What happens to `record_version` / optimistic locking — would cross-org upserts race?
- What happens to `source_providers`, `last_enriched_at`, `last_operation_id` — these are currently per-org-per-entity metadata. In a global model, they reflect whoever enriched last, regardless of org.

**5c. Every code path that filters entity tables by `org_id`.** List every file, function, and line number. This includes:
- Query endpoints in `entities_v1.py`
- Internal upsert endpoints in `internal.py`
- Entity state service functions in `entity_state.py`
- Entity timeline functions in `entity_timeline.py`
- Entity snapshot functions
- Freshness check functions
- Any Trigger.dev code that passes org context for entity operations

### Section 6: Dedicated Tables — What Would Change

For each dedicated table (`icp_job_titles`, `company_customers`, `company_ads`, `gemini_icp_job_titles`, `salesnav_prospects`, `company_intel_briefings`, `person_intel_briefings`, `extracted_icp_job_title_details`), document:

- Current conflict key (from the migration schema definition — trace the actual `CREATE UNIQUE INDEX`)
- Whether `org_id` is part of the conflict key
- What happens if `org_id` is removed from the conflict key — would records from different orgs merge? Would that make sense semantically? (e.g., ICP job titles for a company might differ by org because each org has different ICPs. Company customers might differ because discovery depends on the source company's context.)
- Every code path that writes and reads with `org_id`

**Key insight the executor should evaluate:** Dedicated tables are fundamentally different from entity tables. Entity tables represent facts about the real world (a company IS at this domain). Dedicated tables often represent org-specific analysis results (these are the ICP job titles FOR THIS ORG'S campaign targeting this company). Document which dedicated tables are candidates for globalization and which are inherently org-specific.

### Section 7: Execution Lineage — What Stays Org-Scoped

Even in a fully global entity model, execution lineage (who ran what, when, with what result) should almost certainly stay org-scoped. Document:

- Which tables are execution lineage: `submissions`, `pipeline_runs`, `step_results`, `operation_runs`, `operation_attempts`
- Why they should stay org-scoped (audit, billing, access control, privacy)
- How they currently reference entity data (do they contain entity IDs? `org_id`? domain references?)
- What changes in the join pattern if entities go global but lineage stays org-scoped

### Section 8: Identity Resolution Conflicts

This is the hardest section. The core problem: if Org A enriched example.com via BlitzAPI in February, and Org B enriches example.com via Prospeo in March, what's the canonical record?

Document:
- How entity upserts currently handle conflicting data (trace `upsert_company_entity()` — is it last-write-wins? Is there a merge strategy?)
- How `record_version` and optimistic locking work currently
- What happens with conflicting `canonical_payload` fields — different employee_count values, different LinkedIn URLs, different enrichment data from different providers
- What happens with `source_providers` array — in a global model, this would accumulate providers from all orgs
- Whether there's a concept of "enrichment provenance" — can you tell which org contributed which data to a global entity record?
- Proposed merge strategies, with tradeoffs:
  - **Last write wins** (simplest; loses earlier data)
  - **Most recent enrichment per field** (complex; requires field-level timestamp tracking not currently in the schema)
  - **Append-only enrichment log** (keeps all data; query complexity increases)
  - **Source confidence scoring** (assign provider reliability weights; most complex)

### Section 9: Auth and API Surface Changes

For every endpoint that currently enforces org scoping on entity or dedicated table data, document what would need to change:

- Entity query endpoints (`/api/v1/entities/companies`, `/api/v1/entities/persons`, etc.)
- Dedicated table query endpoints (`/api/v1/icp-job-titles/query`, etc.)
- Internal upsert endpoints (`/api/internal/entity-state/upsert`, etc.)
- Batch submit and status endpoints
- Entity ingest endpoints

For each, answer:
- Does the org filter disappear entirely? Or does it become optional?
- Would tenant users see all entities across all orgs? Is that acceptable?
- Would a new "global read, org-scoped write lineage" pattern be needed?
- What happens to `company_entity_associations` — the sub-org scoping mechanism?
- How would the super-admin auth path change (currently requires `org_id` for entity queries)?

### Section 10: Migration Path

If the decision is made to proceed, what's the actual sequence?

**Phase 1: Schema changes.** What DDL changes are needed? Which unique indexes change? Which columns become nullable or are removed?

**Phase 2: Data migration.** How do you merge duplicate entity records across orgs? Estimate the scale: how many `company_entities` rows would merge (e.g., how many unique `canonical_domain` values exist across all orgs vs. total row count)? What's the merge strategy for conflicting `canonical_payload` values? What happens to `entity_id` references in other tables when two records merge into one?

**Phase 3: Code changes.** Estimate the number of files that would need to change. Group by category:
- Auth dependency changes
- Service function changes (entity upsert, dedicated table services)
- Router changes (query endpoints, internal endpoints)
- Trigger.dev changes (pipeline orchestration, internal API client)
- Test changes

**Phase 4: API contract changes.** Would any public API contracts break? Would the response shape of entity queries change? Would existing API tokens / integrations need updates?

**Estimate the overall scope:** number of files, approximate effort classification (small/medium/large/very-large), risk level.

### Section 11: Risks and Tradeoffs

Enumerate at minimum:

1. **Data ownership ambiguity** — who "owns" a global entity? If Org A enriched it first, does Org B benefit from that enrichment without paying? What about provider credit costs?
2. **Privacy implications** — can Org A see that Org B enriched the same company? Can they see Org B's enrichment data? Is there a business reason to keep enrichment results private per org?
3. **Rollback difficulty** — once entities are merged, can you un-merge them? What's the reversibility of the migration?
4. **Clay-ingested data impact** — 45,591 company entities were ingested under Substrate org. In a global model, these become shared. Is that desired?
5. **Enrichment cost fairness** — if Org A pays for a BlitzAPI enrichment and it becomes globally visible, Org B gets it for free. Is that a product problem?
6. **Migration complexity for existing data** — 45,679 company entities, 2,116 persons, plus all dedicated table rows. What's the dedup/merge complexity?
7. **Concurrent enrichment races** — in a global model, two orgs enriching the same entity simultaneously create upsert races. The optimistic locking (`record_version`) would cause one to fail. Is that acceptable?
8. **Dedicated table semantic mismatch** — ICP job titles are org-specific (each org has different ICPs). Globalizing these doesn't make semantic sense. But company customers might be globally true. Document which tables fit and which don't.

### Section 12: Alternative Approaches

Document at least three alternatives to full globalization, with pros and cons for each:

**Alternative A: Shared reference layer + org-scoped enrichment overlay.**
Global entities exist as a reference (like FMCSA data). Each org's enrichment results are stored as org-scoped overlays that reference the global entity. Queries merge the global base with the org-specific overlay.

**Alternative B: Copy-on-read with global source of truth.**
A single global entity record is the source of truth. When a tenant queries, they get the global record. When they enrich, the enrichment updates the global record (all orgs benefit). Execution lineage stays org-scoped.

**Alternative C: Hybrid — global entities, org-scoped dedicated tables.**
Entity tables (`company_entities`, `person_entities`, `job_posting_entities`) go global. Dedicated tables (ICP job titles, intel briefings, etc.) stay org-scoped because they represent org-specific analysis, not global facts. This follows the doctrinal distinction between "a company IS at this domain" (global fact) and "these are good ICP titles for this company FOR OUR CAMPAIGN" (org-specific analysis).

For each alternative, document:
- What changes vs. current model
- What changes vs. full globalization
- Implementation complexity
- Data model cleanliness
- Whether it follows the doctrinal principles in `ENTITY_DATABASE_DESIGN_PRINCIPLES.md`

### Section 13: Recommendation

Based on the full analysis, state a recommendation. This should be one of:
- Proceed with full globalization — here's the path
- Proceed with a specific alternative — here's why
- Do not proceed — the costs outweigh the benefits given current scale and usage patterns
- Defer — the analysis reveals prerequisites that should be addressed first (e.g., fix the broken auto-persist paths before touching the data model)

Support the recommendation with evidence from the analysis sections. Include any prerequisites or sequencing dependencies.

---

## Deliverable 2: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: produced Global Data Model Analysis covering current org-scoping inventory (exhaustive table-by-table trace), global data patterns, entity identity resolution impact, dedicated table analysis, execution lineage boundary, auth/API surface changes, migration path estimate, risk inventory, and alternative approaches.

Add a last-updated timestamp at the top of the analysis file in the format `**Last updated:** 2026-03-18T[HH:MM:SS]Z`.

Commit standalone.

---

## What is NOT in scope

- **No code changes.** This is a documentation-only directive. Do not modify any Python, TypeScript, SQL, or configuration files.
- **No migrations.** Do not create or modify migration files.
- **No deploying.** Do not run deploy commands.
- **No pushing.** Commit locally only.
- **No changes to CLAUDE.md.** The chief agent decides when to update CLAUDE.md.
- **No changes to existing documentation files.** The only files modified are the new analysis doc and the work log.
- **No production database queries.** Use the production state documented in `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` for row counts and table inventories.

## Commit convention

Two commits total: one for the analysis document, one for the work log entry. Do not push.

## When done

Report back with:
(a) **Table inventory:** total count of org-scoped tables found, broken down by identity-scoping / visibility-scoping / lineage-tracking classification
(b) **Entity identity resolution finding:** for each entity table, does `org_id` participate in the natural key lookup? What exactly would break?
(c) **Dedicated table classification:** which dedicated tables are candidates for globalization vs. inherently org-specific?
(d) **Code impact estimate:** approximate file count that would need changes, grouped by category
(e) **Recommendation:** the bottom-line recommendation from Section 13
(f) **Anything to flag:** surprises in the code that contradict documentation, edge cases in identity resolution, undocumented org_id usage, or anything that changes the calculus of this decision
