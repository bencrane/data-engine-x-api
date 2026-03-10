# Entity Database Design Principles

This document defines the principles that govern how the entity database is designed. Every schema decision, table creation, column addition, and naming choice must follow these rules. AI agents working on entity database schema must read this file before making any changes.

---

## 1. Tables Are Named for What the Data Is, Not Where It Came From

A table represents a concept - a type of entity, a type of relationship, a type of attribute. It does not represent a provider, a tool, or an API.

**Right:** `icp_job_titles`, `company_customers`, `company_ads`
**Wrong:** `gemini_icp_job_titles`, `parallel_case_studies`, `claygent_customers`, `leadmagic_company_enrichment`

If two providers produce the same type of data, the data goes in the same table with a column indicating the source. You should never need a new table just because you added a new provider.

---

## 2. Provider Attribution Lives in Metadata, Not in Structure

Every record should be traceable to its source. But the source is a property of the record, not a property of the table or column.

Use columns like:
- `source_provider` - which provider produced this data
- `source_operation_id` - which operation produced this data
- `source_run_id` - which pipeline run produced this data
- `discovered_at` - when this data was first observed

Do not:
- Name tables after providers
- Name columns after providers (e.g., `leadmagic_email`, `prospeo_email`)
- Create provider-specific tables for the same data type
- Duplicate table structures because a new provider was added

---

## 3. Entities Are Global, Not Tenant-Scoped

A company is a company. A person is a person. These exist independently of which client requested the data or which tenant triggered the enrichment.

Entity tables (companies, people, job postings) do not have `org_id` as a scoping mechanism. The entity record is the same regardless of who asked for it.

The association between a client and the entities relevant to them is a separate concern - handled through tagging, assignment tables, or lineage tracing in the orchestration layer. Not through duplicating entity records per tenant.

---

## 4. One Entity, One Record

Each real-world entity has exactly one record in the entity table. If Prospeo says Acme Corp has 450 employees and BlitzAPI says 500, those are two data points about one entity - not two entities.

Identity resolution determines which record a data point belongs to. Deduplication prevents the same entity from having multiple records. Conflicting data points are resolved through merge rules (e.g., most recent wins, highest confidence wins), not by storing multiple versions as separate rows.

The enrichment history (which provider said what, when) lives in the enrichment log, not in the entity record itself. The entity record holds the current best-known state.

---

## 5. Raw Payloads Are Preserved but Separated

Every provider response should be stored in its complete, unmodified form. This is non-negotiable - you may need to re-extract data later as requirements change.

But raw payloads do not belong in the entity tables. They belong in the orchestration/operations layer where the API call was made. The entity database receives the extracted, canonical result - not the raw blob.

The link between the entity record and its raw source is maintained through lineage columns (`source_run_id`, `source_operation_id`) that point back to the orchestration layer where the raw payload lives.

---

## 6. Enrichment History Is Explicit

For every entity, you must be able to answer:
- When was this entity last enriched?
- Which provider supplied this data point?
- Did we attempt enrichment and get no result, or did we never attempt it?
- How fresh is this data?

This requires an enrichment log - a record of every enrichment attempt per entity, with provider, timestamp, status (success / no_result / error), and a reference to the raw payload.

The entity record itself carries summary fields (`last_enriched_at`, `source_providers`) for quick access. The enrichment log carries the full history.

---

## 7. Schema Reflects Data Concepts, Not Pipeline Steps

Tables should map to business concepts:
- `companies` - real-world companies
- `people` - real-world people
- `company_customers` - customer relationships between companies
- `icp_job_titles` - ideal customer profile titles for a company
- `company_ads` - advertisements run by a company

Tables should NOT map to pipeline steps, operations, or processing stages. If a pipeline step produces ICP job titles, the output goes in `icp_job_titles` - not in a table named after the step or the pipeline.

Processing-stage tables (`raw_*`, `staging_*`, `extracted_*`) belong in the orchestration layer, not in the entity database. The entity database only holds canonical, ready-to-consume data.

---

## 8. Columns Are Typed and Indexed for Their Access Pattern

If a column will be used for filtering, grouping, or joining, it should be a typed column with an appropriate index. Do not store queryable data inside JSONB blobs.

JSONB is appropriate for:
- Flexible metadata that varies per record
- Data that is written once and rarely queried (e.g., raw payload references)
- Supplementary fields that don't justify their own column yet

JSONB is NOT appropriate for:
- Fields you will filter by (e.g., industry, employee count, location)
- Fields you will group by in reports (e.g., source provider, enrichment status)
- Fields that have a consistent structure across all records

When in doubt, make it a column. You can always consolidate into JSONB later. You cannot efficiently query JSONB without GIN indexes, and even those are slower than B-tree indexes on typed columns.

---

## 9. Relationships Are First-Class, Not Implied

If two entities are related (a person works at a company, a company is a customer of another company), that relationship gets its own table or a dedicated column with a foreign key.

Do not rely on:
- Matching text values across tables (e.g., joining on `domain` strings without FK constraints)
- Implied relationships from shared columns
- JSONB arrays of related entity IDs

Relationships should have: source entity, target entity, relationship type, valid_from, valid_until (if temporal), and source attribution.

---

## 10. Naming Conventions

**Tables:** Plural nouns describing the entity or concept. `companies`, `people`, `company_customers`, `icp_job_titles`, `enrichment_log`.

**Columns:** Snake_case, descriptive, no abbreviations. `canonical_domain`, `last_enriched_at`, `source_provider`, `employee_count`.

**No provider names** in table or column names. Ever.

**No processing stage names** in the entity database. No `raw_`, `extracted_`, `staging_` prefixes. Those belong in the orchestration layer.

**Consistent timestamp columns:** Every table gets `created_at` and `updated_at`. Entity tables also get `last_enriched_at`.

---

## 11. Additive Changes Only

The entity database schema should grow by adding tables and columns, not by restructuring existing ones. If a new provider supplies a new type of data:

- If an appropriate table exists, add the data to it with proper source attribution
- If no appropriate table exists, create one named for the data concept
- Never modify an existing table's primary purpose to accommodate a new provider

---

## Summary Checklist for Schema Reviews

Before approving any schema change, verify:

- [ ] No table is named after a provider or tool
- [ ] No column is named after a provider or tool
- [ ] Provider attribution is in metadata columns, not structure
- [ ] Entity records are not duplicated per tenant
- [ ] Raw payloads are not stored in entity tables
- [ ] Queryable fields are typed columns, not buried in JSONB
- [ ] Relationships use foreign keys, not implicit text matching
- [ ] `created_at`, `updated_at`, and (for entities) `last_enriched_at` are present
- [ ] The table is named for what the data IS, not how it was produced
