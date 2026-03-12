# Directive: FMCSA COPY-Based Bulk Write Path Plan

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA bulk ingestion path in `app/services/fmcsa_daily_diff_common.py` was already improved once by moving from Supabase PostgREST to direct Postgres via `psycopg` `executemany`. That is still not good enough. `executemany` with parameterized `INSERT ... ON CONFLICT` remains too slow for the largest FMCSA feeds, especially when batches contain hundreds of thousands or millions of rows. Feeds that should finish in minutes are taking 1-2+ hours. The correct end-state is a COPY-based bulk load pipeline: bulk load into a temp staging table, then merge into the target table with a single set-based upsert. This directive is planning only. Your job in this phase is to produce a comprehensive implementation plan document that I can review and revise before any code is changed.

**Locked target architecture for the future implementation:**

- Phase 1: bulk load each batch into a temporary staging table using `psycopg` `cursor.copy()` and `COPY ... FROM STDIN`
- Phase 2: merge from staging into the target table with one `INSERT ... SELECT ... ON CONFLICT (...) DO UPDATE` statement
- same FastAPI endpoint contracts
- same Trigger JSON batch payloads
- same FMCSA write semantics
- larger Trigger-side batch sizes once the COPY path exists

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `/Users/benjamincrane/data-engine-x-api/app/services/fmcsa_daily_diff_common.py`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/023_fmcsa_snapshot_history_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/024_fmcsa_sms_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/025_fmcsa_remaining_csv_export_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/fmcsa-daily-diff.ts`
- `/Users/benjamincrane/data-engine-x-api/tests/test_fmcsa_daily_diff_persistence.py`

---

### Deliverable 1: COPY Migration Implementation Plan

Create `docs/FMCSA_COPY_BULK_WRITE_PLAN.md`.

This is a planning deliverable only. Do not implement the COPY path yet.

The plan document must be specific enough that a later executor can implement it without rethinking the architecture from scratch.

Required sections:

- current-state diagnosis
- exact bottleneck in the current `executemany` path
- target COPY-based architecture
- temp-table design
- COPY serialization format
- merge/upsert SQL semantics
- error handling and cleanup strategy
- Trigger batch-size changes
- test strategy
- rollout and verification strategy
- risks / open questions

The plan must explicitly cover the following implementation details:

1. **Phase 1 staging-table approach**
- how the temp table will be created
- whether it will use `CREATE TEMP TABLE ... (LIKE entities.target_table INCLUDING DEFAULTS)` or explicit projected columns
- whether the plan will COPY all target-table columns or a narrower explicit column set
- how temp table naming and lifecycle will work inside one connection / transaction

2. **Phase 2 merge/upsert behavior**
- exact conflict target behavior
- how the future merge will preserve the same conflict semantics as the current path
- same conflict key:
  - `feed_date`
  - `source_feed_name`
  - `row_position`
- same insert-only field semantics:
  - `created_at`
  - `record_fingerprint`
  - `first_observed_at`
- same update-on-conflict semantics:
  - `updated_at`
  - `last_observed_at` for snapshot/history tables
  - all other mutable typed/business/metadata columns that currently update
- how legacy fallback conflict behavior will be treated if any live table still relies on `record_fingerprint`

3. **COPY serialization details**
- how JSONB columns will be serialized for COPY:
  - `raw_source_row`
  - `source_run_metadata`
- how dates will be represented
- how timestamps will be represented
- how NULLs will be represented
- how empty strings vs NULLs will be preserved
- how special characters, delimiters, tabs/newlines, and Unicode will be handled safely
- whether the plan will use text COPY, CSV COPY, or binary COPY, and why

4. **Table-shape coverage**
- explain how the plan handles at least these three shape classes:
  - one top-5 snapshot/history table
  - one daily/snapshot row table such as `carrier_registrations` or `process_agent_filings`
  - one SMS/CSV table such as `carrier_safety_basic_measures`, `carrier_safety_basic_percentiles`, `carrier_inspections`, or `carrier_inspection_violations`
- call out any table-specific complications the implementation must account for

5. **Error handling and cleanup**
- how the implementation will fail loudly on:
  - temp table creation failure
  - COPY failure
  - merge failure
  - transaction failure
- how temp table cleanup will be guaranteed on both success and failure
- how connection/cursor cleanup will be guaranteed
- whether the plan relies on transaction rollback semantics for cleanup, explicit `DROP TABLE`, or both

6. **Batch-size changes**
- propose the new default batch size of `5000`
- propose `10000` for the largest feeds
- identify exactly which feed configs should get `10000`
- explain how `trigger/src/workflows/fmcsa-daily-diff.ts` should be updated to keep batch size configurable per feed
- explain any FastAPI-side assumptions that must match the larger batch sizes

7. **Testing strategy**
- the plan must go beyond one-row happy-path tests
- include a future test matrix covering:
  - JSONB columns
  - NULL dates
  - empty strings
  - special characters in text fields
  - one daily diff/snapshot table shape
  - one all-history shared table shape
  - one SMS CSV table shape
  - conflict resolution preserving insert-only fields
  - failed COPY with no partial commit
  - failed merge with no partial commit
- specify whether the future tests should be mock-heavy, integration-style against a real Postgres test database, or a mixed strategy, and justify that choice

8. **Verification and rollout**
- how the later implementation should verify row-count correctness
- how it should verify semantic parity with the current path
- how it should verify that larger Trigger batches do not break endpoint behavior
- what evidence would be sufficient to declare the COPY path complete and stop revisiting this layer

Hard requirements for the plan:

- do not write implementation code in this phase
- do not modify `app/services/fmcsa_daily_diff_common.py` yet
- do not change Trigger feed configs yet
- do not create migrations yet
- do not change tests yet
- do not deploy anything
- do not push anything
- do not hand-wave over conflict semantics; read the current implementation and replicate it precisely in the plan
- do not hand-wave over JSONB/NULL/COPY formatting; spell out the intended format choices explicitly

Commit standalone.

---

**What is NOT in scope:** No code implementation. No migrations. No Trigger batch-size changes. No deployment. No push. No direct edits to the FMCSA write path in this phase. No non-FMCSA database work.

**Commit convention:** One commit only for the plan document. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_COPY_BULK_WRITE_PLAN.md`, (b) the exact COPY format and temp-table strategy proposed, (c) the exact conflict/update semantics the later implementation must preserve, (d) the proposed new default and per-feed batch sizes, (e) the proposed test matrix, and (f) anything to flag before implementation begins.
