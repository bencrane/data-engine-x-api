# FMCSA COPY Bulk Write Plan

## Current-State Diagnosis

The FMCSA persistence layer currently converts each parsed row into a typed Python dictionary, adds shared source metadata, intersects that row with the live table columns from `information_schema.columns`, and then writes the batch with one parameterized `INSERT ... ON CONFLICT ... DO UPDATE` statement executed through `psycopg` `cursor.executemany()` in `app/services/fmcsa_daily_diff_common.py`.

This path already improved on the original Supabase PostgREST write pattern because it writes directly to Postgres and preserves loud failure behavior. It is still fundamentally row-oriented:

- each row is individually adapted into Postgres parameters
- each row individually incurs JSONB adaptation for `raw_source_row` and `source_run_metadata`
- each row individually probes the conflict index
- each row individually executes the upsert update logic

That pattern is acceptable for small and moderate feeds, but it is the wrong shape for the largest FMCSA datasets. The repo already treats `Company Census File` and `Vehicle Inspection File` as large-file feeds with streaming parse and chunked confirmed writes, and the all-history / wide CSV-export families can also produce very large write volumes. The remaining bottleneck is now the row-by-row database write path rather than download or parsing.

## Exact Bottleneck In The Current `executemany` Path

The current hot path is the `cursor.executemany()` call in `upsert_fmcsa_daily_diff_rows()`.

Why it is too slow:

- `executemany()` still issues a parameterized upsert per row rather than one set-based merge.
- Every row repeats placeholder binding and type adaptation, including JSONB wrapping.
- PostgreSQL still performs conflict detection and update evaluation row-by-row.
- Wide FMCSA rows make the per-row cost worse because many typed columns and two JSONB columns are rebound for every row.
- Snapshot/history tables also compute and preserve insert-only fields (`record_fingerprint`, `first_observed_at`) on a per-row basis before hitting the database.

The result is that feeds which should be limited mainly by raw I/O and index maintenance are instead limited by Python-to-Postgres parameter marshaling plus repeated single-row upsert work.

## Target COPY-Based Architecture

The future implementation should keep the existing FastAPI endpoint contracts, Trigger payload shape, row builders, and FMCSA source semantics. Only the internal bulk-write mechanism changes.

Future write flow:

1. Build the same typed per-row dictionaries that the current services already produce.
2. Intersect each row with the live target-table columns exactly as the current path does.
3. Create a temporary staging table on the same Postgres connection and inside the same transaction.
4. Bulk load the batch into that temp table using `psycopg` `cursor.copy()` and `COPY ... FROM STDIN`.
5. Merge from staging into the real `entities` target table with one `INSERT ... SELECT ... ON CONFLICT (...) DO UPDATE` statement.
6. Commit on success; roll back on any failure.

This preserves:

- the same FastAPI request and response contract
- the same Trigger JSON batch payload shape
- the same row-builder typing logic
- the same per-feed source metadata
- the same conflict/update semantics

## Temp-Table Design

### Creation Strategy

The staging table should be created with:

- `CREATE TEMP TABLE ... (LIKE entities.<target_table> INCLUDING DEFAULTS) ON COMMIT DROP`

This is the right choice over hand-maintained explicit temp-table column DDL because it guarantees that the staging column types stay aligned with the live target table, including:

- `JSONB`
- `DATE`
- `TIMESTAMPTZ`
- `NUMERIC`
- `BOOLEAN`
- defaults such as `created_at`, `updated_at`, and primary-key UUID defaults

### Why `LIKE ... INCLUDING DEFAULTS` But A Narrower Projected COPY Column Set

The future implementation should not COPY every physical target-table column just because the temp table contains them. It should COPY a narrower explicit column set derived from the same logic used today:

1. build the typed row with the feed-specific `row_builder`
2. add shared FMCSA metadata fields
3. add snapshot/history-specific fields when applicable
4. intersect that row with the live table columns returned by `information_schema.columns`

Reasons to keep the explicit projected column set narrower than the full table:

- it preserves the current live-schema compatibility behavior
- it supports legacy top-5 tables whose live column set may still drift from the latest repo schema
- it avoids copying generated columns such as `id`
- it keeps sparse shared-table writes safe when one feed shape populates fewer columns than another feed shape sharing the same table

### Temp Table Naming And Lifecycle

The future implementation should create a unique temp-table name per write call, for example:

- fixed prefix
- target table name
- short random or monotonic suffix

Requirements:

- the name must be SQL-identifier-safe and quoted exactly like the existing target-table quoting helpers do
- the table must exist only inside one connection / transaction scope
- one invocation of `upsert_fmcsa_daily_diff_rows()` should use one connection, one transaction, one temp table

Lifecycle:

- create temp table after opening the transaction
- COPY rows into temp table
- merge temp table into target
- rely on `ON COMMIT DROP` for the success path
- also use rollback and best-effort explicit drop for failure cleanup while the connection is still open

## COPY Serialization Format

### Chosen Format

The future implementation should use PostgreSQL text COPY, not CSV COPY and not binary COPY.

Why text COPY is the right fit:

- simpler than binary COPY
- more explicit than CSV COPY for preserving `NULL` versus empty string
- easy to reason about for mixed `TEXT`, `DATE`, `TIMESTAMPTZ`, numeric, boolean, and `JSONB` columns
- safe for very wide rows and raw-source JSON payloads when proper escaping is applied

### Exact Serialization Rules

The future implementation should lock the following text COPY conventions:

- encoding: UTF-8
- field delimiter: tab
- row delimiter: newline
- `NULL` representation: `\\N`
- empty string representation: empty field, not `\\N`

Value formatting rules:

- `DATE` values: ISO `YYYY-MM-DD`
- `TIMESTAMPTZ` values: ISO 8601 UTC strings matching the current `utc_now_iso()` / `source_observed_at` behavior
- booleans: PostgreSQL text COPY boolean literals accepted by the destination type
- integers / numerics: plain string form with no locale formatting

JSONB column handling:

- `raw_source_row`
- `source_run_metadata`

Those columns should be serialized as compact JSON text and then passed through the same text-COPY escaping rules as any other text field before writing into the COPY stream.

### Preserving `NULL` vs Empty Strings

This layer must preserve the current semantic distinction:

- Python `None` becomes `\\N`
- empty string stays empty string

That distinction matters because several FMCSA tables intentionally treat blank strings differently from missing values, and many tests already lock that behavior.

### Special Characters And Safety

The text COPY writer must escape at minimum:

- backslash
- tab
- newline
- carriage return

Practical rule:

- `\` -> `\\`
- tab -> `\t`
- newline -> `\n`
- carriage return -> `\r`

This preserves:

- raw text containing delimiters
- embedded newlines in source text
- JSON strings containing quotes, slashes, or Unicode
- any FMCSA text field containing unusual punctuation or control characters

Unicode should be preserved as UTF-8 text. No lossy normalization should be introduced.

## Merge / Upsert SQL Semantics

### Conflict Target

The future merge must preserve the exact conflict-selection behavior in `app/services/fmcsa_daily_diff_common.py`.

Primary conflict target:

- `feed_date`
- `source_feed_name`
- `row_position`

Legacy fallback conflict target:

- `record_fingerprint`

Selection rule:

- if the live/projected columns include the 3-column FMCSA source key, use that
- otherwise, if the live/projected columns include `record_fingerprint`, use that
- otherwise fail loudly because no valid live conflict target exists

### Insert-Only Fields That Must Never Update On Conflict

The later implementation must preserve these insert-only semantics exactly:

- `created_at`
- `record_fingerprint`
- `first_observed_at`

Those values are set on first insert and must survive later same-slot reruns unchanged.

### Fields That Must Update On Conflict

The later implementation must preserve current mutable-column behavior:

- `updated_at` always updates
- `last_observed_at` updates for snapshot/history tables
- every other mutable typed/business/source/raw-metadata column currently included in the row projection updates from the staged row

The merge must not update:

- conflict-target columns
- the insert-only fields listed above

### Snapshot / History Semantics

The current code treats these as snapshot/history tables:

- `operating_authority_histories`
- `operating_authority_revocations`
- `insurance_policies`
- `insurance_policy_filings`
- `insurance_policy_history_events`

For those tables, the later COPY path must preserve:

- `record_fingerprint` generation when the column exists
- `first_observed_at` populated on first insert only
- `last_observed_at` refreshed on conflict update

### Legacy Fallback Behavior

If any live top-5 table still relies on legacy `record_fingerprint` uniqueness rather than the newer `(feed_date, source_feed_name, row_position)` key, the future implementation must not force a migration inside this workstream.

Instead it must:

- continue computing `record_fingerprint` with the current deterministic formula based on table name, feed date, feed name, and row position
- use `record_fingerprint` as the merge conflict target for that live schema
- preserve rerun idempotency and insert-only timestamps exactly as the current path does

## Table-Shape Coverage

The later implementation must explicitly work across at least these three shape classes.

### 1. Top-5 Snapshot / History Table Example: `operating_authority_histories`

Complications:

- may still need legacy `record_fingerprint` fallback on some live schemas
- carries `first_observed_at` and `last_observed_at`
- uses source-row identity, not business-row deduplication

Required preservation:

- same-row same-feed same-day reruns update the source slot
- `first_observed_at` stays frozen
- `last_observed_at` advances

### 2. Daily / Snapshot Shared Table Example: `carrier_registrations`

Complications:

- daily and `Carrier - All With History` share one target table
- the two feeds must remain distinct because `source_feed_name` is part of row identity
- the persistence layer must remain agnostic to upstream header alias normalization

Required preservation:

- `Carrier` and `Carrier - All With History` rows for the same `feed_date` and same `row_position` remain separate source observations
- same-day reruns for the same feed overwrite only that feed’s source slot

### 3. SMS / CSV Shared Table Example: `carrier_inspections`

Complications:

- `SMS Input - Inspection` and `Vehicle Inspection File` share one destination table
- the CSV-export feed populates a much wider column set than the SMS subset
- the row projection must tolerate sparse writes safely

Required preservation:

- the later COPY path should stage and merge only the columns present in the built row and supported by the live table
- wider Vehicle Inspection File writes must not force unrelated nullification semantics beyond the current update behavior

## Error Handling And Cleanup Strategy

The COPY path must fail loudly. It must not introduce a silent-success branch.

The implementation should explicitly surface failures for:

- temp table creation failure
- COPY failure
- merge failure
- transaction commit failure

### Transaction Model

One invocation of `upsert_fmcsa_daily_diff_rows()` should use:

- one direct Postgres connection
- one explicit transaction
- one temp-table lifecycle

Required behavior:

- if temp-table creation fails, abort immediately
- if COPY fails, roll back the transaction and surface the exception
- if merge fails, roll back the transaction and surface the exception
- if commit fails, surface that failure and do not claim rows were written

### Cleanup Guarantees

Cleanup should rely on both transaction semantics and explicit cleanup:

- primary success cleanup: `ON COMMIT DROP`
- failure cleanup: transaction rollback
- best-effort explicit cleanup: `DROP TABLE IF EXISTS` on the temp table while the connection is still open

Connection and cursor cleanup should continue to use context-manager ownership so that:

- cursor close is guaranteed
- connection close is guaranteed
- rollback-on-exception is not skipped

## Trigger Batch-Size Changes

The future implementation should raise Trigger-side batch sizes only after the COPY path exists.

### Proposed Defaults

- new shared-workflow default batch size: `5000`

This replaces the current implicit default of `500`.

### Explicit `10000` Overrides For The Largest Feeds

The future plan should set `writeBatchSize: 10000` only for:

- `FMCSA_COMPANY_CENSUS_FILE_FEED`
- `FMCSA_VEHICLE_INSPECTION_FILE_FEED`

Why only those two:

- the repo already treats them as the clearly large-file cases
- they currently run with the most conservative write batch sizes
- they are the strongest candidates to benefit from materially larger batches once row-oriented upsert overhead is removed

All other feeds should initially inherit the new `5000` default unless later runtime evidence proves a narrower override is still needed.

### Trigger Workflow Contract Changes

The future Trigger change should remain config-driven inside `trigger/src/workflows/fmcsa-daily-diff.ts`:

- keep `writeBatchSize` as an optional per-feed config
- change the fallback from `500` to `5000`
- preserve feed-specific overrides where explicitly set

### FastAPI-Side Assumptions

The FastAPI contract must stay unchanged:

- same internal endpoint paths
- same JSON shape
- same `records: list[InternalFmcsaDailyDiffRow]`
- same response payload shape

Only batch cardinality changes. The server-side assumption that must continue to hold is:

- one request batch is processed in one DB transaction and returns one write summary

## Test Strategy

The future implementation should use a mixed strategy:

- keep unit-style tests for row-building, column projection, and conflict-selection logic
- add real-Postgres integration coverage for COPY, temp tables, merge behavior, and rollback safety

A mock-only approach is not sufficient because the most important new behavior is database-native:

- `cursor.copy()`
- temp-table lifecycle
- set-based merge semantics
- transaction rollback guarantees

### Required Future Test Matrix

The later implementation should cover at minimum:

- JSONB round-trip for `raw_source_row`
- JSONB round-trip for `source_run_metadata`
- `NULL` date fields remain `NULL`
- empty strings remain empty strings
- special characters in text fields:
  - tabs
  - newlines
  - backslashes
  - quotes
  - Unicode
- one daily/snapshot table shape such as `carrier_registrations`
- one all-history shared-table shape such as `insurance_policy_history_events` or `process_agent_filings`
- one SMS/CSV shared-table shape such as `carrier_inspections`
- conflict resolution preserves:
  - `created_at`
  - `record_fingerprint`
  - `first_observed_at`
- failed COPY produces no partial commit
- failed merge produces no partial commit
- legacy fallback conflict behavior still works when the live table shape only supports `record_fingerprint`

### Recommended Test Split

Service-level and endpoint-contract tests should remain in the existing FMCSA persistence test suite.

The new COPY-specific coverage should add integration-style tests against a real Postgres test database because only that can prove:

- correct text COPY decoding
- correct JSONB / date / timestamptz typing
- temp-table cleanup behavior
- rollback correctness

## Rollout And Verification Strategy

The later implementation should be verified in two layers:

- semantic parity with the current write path
- throughput improvement under larger Trigger batches

### Row-Count Verification

The future executor should verify:

- staged row count equals input batch size
- merge input row count equals staged row count
- returned `rows_received` equals request row count
- returned `rows_written` continues to represent rows processed by the batch write path

Because this is an upsert path, final target-table row counts must be interpreted alongside conflict behavior. Verification should distinguish:

- first insert of a source slot
- same-slot rerun update
- different-feed or different-feed-date insert

### Semantic-Parity Verification

The later implementation should prove that the COPY path preserves current behavior for:

- same `feed_date`
- same `source_feed_name`
- same `row_position`
- different `source_feed_name` values sharing one destination table
- snapshot/history insert-only fields
- shared-table sparse/wide feed variants

### Trigger-Batch Verification

The later implementation should verify that larger Trigger batches:

- do not change endpoint request or response contracts
- do not break confirmed-write validation
- do not cause partial-write ambiguity
- remain compatible with existing per-feed timeout / runtime settings

### Evidence Required To Declare This Layer Complete

The COPY path should be considered complete when all of the following are true:

- no targeted FMCSA bulk path still relies on row-oriented `executemany` for the final upsert work
- the real-Postgres COPY / merge / rollback tests pass
- existing FMCSA semantic-parity tests still pass
- Trigger workflow tests lock the new `5000` default and the `10000` overrides for the two largest feeds
- representative large-feed runs show materially lower write latency than the current path
- no endpoint contract changes were required

## Risks / Open Questions

### 1. Live-Schema Drift In Top-5 Tables

The repo schema now prefers `(feed_date, source_feed_name, row_position)`, but some live top-5 tables may still depend on `record_fingerprint`. The executor must preserve runtime compatibility rather than assuming uniform schema state.

### 2. Large Internal Request Bodies

Moving from `500` to `5000` and `10000` rows will materially increase JSON request sizes between Trigger and FastAPI. That is acceptable as the target plan, but the implementation must verify that current internal HTTP limits and timeout behavior remain safe.

### 3. COPY Escaping Is A Correctness Concern

This work will fail semantically if COPY escaping is treated casually. The implementation must validate tabs, newlines, backslashes, Unicode, and JSONB payloads with real database tests.

### 4. Shared-Table Sparse Updates Need Care

For shared tables such as `carrier_inspections` and `motor_carrier_census_records`, the implementation must preserve current row-projection behavior so one feed shape does not accidentally redefine another feed shape’s storage contract.

### 5. No Migration Is Included In This Phase

This plan intentionally does not create migrations or force schema convergence. The future executor must work with the live table shape discovered at runtime and only use fallback behavior where the current code already does so.
