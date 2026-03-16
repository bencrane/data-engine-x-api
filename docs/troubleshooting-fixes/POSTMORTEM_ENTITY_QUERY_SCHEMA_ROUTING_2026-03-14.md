# Post-Mortem: Entity Query Endpoints Returning Empty / "Not Found"

**Date:** 2026-03-14
**Severity:** P1 — Frontend completely unable to load companies or persons
**Duration:** Unknown (broken since migration 021 deployed; surfaced when frontend integration began)
**Commit fix:** 84b9490

## What Happened

The frontend called `POST /api/v1/entities/companies` and `POST /api/v1/entities/persons` and received "Not Found" / empty results. The endpoints were live and authenticated correctly, but every query returned zero rows.

## Root Cause

Migration 021 moved all entity tables (`company_entities`, `person_entities`, `job_posting_entities`, `entity_timeline`, `entity_snapshots`) from the `public` schema to the `entities` schema. The query endpoints in `app/routers/entities_v1.py` were never updated — they used `client.table("company_entities")` which defaults to `public`, hitting tables that no longer exist there.

The same bug existed in `app/services/external_ingest.py` for the `_resolve_company_by_domain` lookup.

## Affected Endpoints

| Endpoint | Table | File:Line |
|---|---|---|
| `POST /api/v1/entities/companies` | `company_entities` | `entities_v1.py:191` |
| `POST /api/v1/entities/persons` | `person_entities` | `entities_v1.py:252` |
| `POST /api/v1/entities/job-postings` | `job_posting_entities` | `entities_v1.py:330` |
| `POST /api/v1/entities/timeline` | `entity_timeline` | `entities_v1.py:423` |
| `POST /api/v1/entities/snapshots` | `entity_snapshots` | `entities_v1.py:477` |
| `POST /api/v1/entities/ingest` (domain lookup) | `company_entities` | `external_ingest.py:196` |

## Fix

Added `.schema("entities")` before `.table(...)` on all 6 call sites.

## Why This Was Missed

1. Migration 021 was a schema-split migration. The entity upsert services (`entity_state.py`) were updated at the time, but the read-only query endpoints in `entities_v1.py` were not.
2. No integration tests cover the entity list endpoints against a live database with the `entities` schema.
3. The ingest endpoint (`/entities/ingest`) happened to work for writes because `upsert_company_entity` / `upsert_person_entity` in `entity_state.py` already used the correct schema — only the domain-lookup helper in `external_ingest.py` was broken.

## Prevention Rules

1. **Any migration that moves or renames tables must include a full grep for every affected table name across the entire codebase.** The grep must cover `app/routers/`, `app/services/`, `trigger/src/`, and `scripts/`. Every `client.table("<table_name>")` call site must be verified.
2. **Schema-qualified queries are mandatory for all entity tables.** Every Supabase query against an entity table must use `client.schema("entities").table(...)`. A bare `client.table(...)` call for any entity table is a bug.
3. **When answering questions about existing endpoints, read the implementation first.** Do not rely on route registration alone to confirm an endpoint works — verify the query actually hits the right schema/table.
