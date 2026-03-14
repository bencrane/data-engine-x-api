**Directive: FMCSA Ingest Pipeline Performance Fixes — Eliminate Server-Side Bottlenecks**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA staged artifact ingest pipeline takes 36+ minutes for the SMS Motor Carrier Census feed (2.1M rows, 43 columns) on a `large-2x` Trigger.dev machine. Performance diagnosis confirmed that ~75-85% of the time (25-30 minutes) is spent in the FastAPI-side upsert path (Phase 7), not in the Trigger.dev download/parse/upload phases (~7-10 minutes). Three specific bottlenecks drive the server-side slowness:

1. **`raw_values` duplication in NDJSON artifacts.** Each row serializes the same data twice: once as `raw_values: string[]` and once as `raw_fields: Record<string, string>`. No row builder ever reads `raw_values`. It is only preserved in the `raw_source_row` JSONB column, where it doubles the JSONB payload size for zero business value. For 2.1M rows × 43 columns, this adds ~700MB-1GB to the NDJSON artifact and proportionally inflates gzip, upload, download, decompress, parse, and JSONB TOAST write times.

2. **Conservative chunk size.** `DEFAULT_CHUNK_SIZE = 10_000` means 210 sequential chunk upserts for 2.1M rows. Each chunk pays fixed overhead: acquire connection, `CREATE TEMP TABLE`, `COPY`, `INSERT...ON CONFLICT`, `COMMIT`, release connection. Increasing to 50,000 rows per chunk reduces this to 42 chunks — same total data, ~80% less DDL overhead.

3. **ON CONFLICT upsert for snapshot feeds.** Every FMCSA table uses `UNIQUE(feed_date, source_feed_name, row_position)` as the conflict target. For full-snapshot feeds (where each run replaces all rows for a given `feed_date + source_feed_name`), the ON CONFLICT merge forces Postgres to check the unique index for every row. A DELETE-then-INSERT strategy for the same `(feed_date, source_feed_name)` scope eliminates conflict resolution overhead entirely, since no conflicting rows exist after the delete.

**Combined target:** SMS Motor Carrier Census (2.1M rows) should complete end-to-end in under 15 minutes. These three fixes are estimated to save 15-20 minutes combined.

**Current architecture (as of 2026-03-13):**

The artifact ingest flow relevant to this directive:

1. **Trigger.dev** downloads CSV, parses rows, calls `normalizeCsvRow()` which produces `{ row_number, raw_values, raw_fields }`, writes NDJSON lines to temp file, gzips, uploads to Supabase Storage, sends manifest POST to FastAPI.

2. **FastAPI** receives manifest at `/api/internal/fmcsa/ingest-artifact`, downloads the gzipped artifact from Supabase Storage, decompresses line-by-line, accumulates chunks of `DEFAULT_CHUNK_SIZE` rows, calls the per-feed `upsert_func(source_context, rows)` for each chunk.

3. **Per-chunk upsert** in `upsert_fmcsa_daily_diff_rows()`: runs `row_builder()` on each row (accesses only `row["raw_fields"]`), adds metadata columns including `raw_source_row` JSONB (which stores the full `FmcsaDailyDiffRow` including `raw_values`), creates temp table, COPY rows in, `INSERT...ON CONFLICT DO UPDATE`, commit.

**Verified facts from code analysis:**

- `raw_values` is **never read** by any Python row builder. All 18 row builders access `row["raw_fields"]` exclusively. `raw_values` is only stored in the `raw_source_row` JSONB column.
- `raw_source_row` is **write-only audit data**. No API endpoint, no query, no downstream process ever reads it. No indexes exist on it.
- All 31 feeds use the same conflict target: `(feed_date, source_feed_name, row_position)`.
- `row_position` is sequential per run (1, 2, 3, ..., N). Each run for a given `(feed_date, source_feed_name)` is a complete snapshot — there is no incremental append across runs.
- `FMCSA_SNAPSHOT_HISTORY_TABLES` (5 tables) get extra fields (`record_fingerprint`, `first_observed_at`, `last_observed_at`). The other tables do not.

**Existing code to read:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — especially:
  - `FmcsaDailyDiffRow` type (line ~71) — the shape with `raw_values` and `raw_fields`
  - `normalizeCsvRow()` (line ~400) — where `raw_values` is assigned
  - `buildNdjsonGzipped()` (line ~543) — non-streaming path (must also drop `raw_values`)
  - `parseAndPersistStreamedCsv()` (lines ~740–881) — streaming path
- `trigger/src/workflows/__tests__/fmcsa-artifact-ingest.test.ts` — tests that reference `raw_values`
- `app/services/fmcsa_artifact_ingest.py` — `ingest_artifact()`, `DEFAULT_CHUNK_SIZE`
- `app/services/fmcsa_daily_diff_common.py` — `FmcsaDailyDiffRow` TypedDict, `upsert_fmcsa_daily_diff_rows()`, `_build_fmcsa_bulk_merge_sql()`, `FMCSA_CONFLICT_COLUMNS`, `FMCSA_SNAPSHOT_HISTORY_TABLES`
- `app/services/motor_carrier_census_records.py` — representative row builder (only accesses `raw_fields`)
- `tests/test_fmcsa_daily_diff_persistence.py` — Python tests that may reference `raw_values`
- `tests/test_fmcsa_artifact_ingest.py` — Python artifact ingest tests

---

### Deliverable 1: Drop `raw_values` from the NDJSON Artifact

Remove `raw_values` from the data shape that flows through the artifact pipeline. This eliminates the largest source of payload bloat.

**TypeScript changes:**

- In `FmcsaDailyDiffRow` interface (line ~71): remove the `raw_values` field.
- In `normalizeCsvRow()` (line ~400): remove `raw_values: values` from the returned object.
- In `buildNdjsonGzipped()` (line ~543): no change needed — it serializes whatever `FmcsaDailyDiffRow` contains.

**Python changes:**

- In `FmcsaDailyDiffRow` TypedDict (`fmcsa_daily_diff_common.py` line ~52): remove the `raw_values` field.
- In `upsert_fmcsa_daily_diff_rows()` (`fmcsa_daily_diff_common.py` line ~403): update the `raw_source_row` construction to exclude `raw_values`. Change from:
  ```
  "raw_source_row": {
      "row_number": row["row_number"],
      "raw_values": row["raw_values"],
      "raw_fields": row["raw_fields"],
  }
  ```
  to:
  ```
  "raw_source_row": {
      "row_number": row["row_number"],
      "raw_fields": row["raw_fields"],
  }
  ```

**Test updates:**

- Update TypeScript test file (`fmcsa-artifact-ingest.test.ts`): remove `raw_values` from test row construction and assertions. The test at line ~101 constructs `FmcsaDailyDiffRow` objects with `raw_values` — remove that field. The assertion at line ~119 checks `parsed0.raw_values` — remove it. The assertion at line ~188 checks `Array.isArray(row0.raw_values)` — remove it.
- Update Python test files: find any test constructing `FmcsaDailyDiffRow` dicts with `raw_values` and remove the field. Find any assertions checking `raw_values` in stored `raw_source_row` and remove them.

**Verification:** After changes, `raw_values` should appear nowhere in the codebase except in git history.

Commit standalone.

### Deliverable 2: Increase Default Chunk Size to 50,000

In `app/services/fmcsa_artifact_ingest.py`, change:

```python
DEFAULT_CHUNK_SIZE = 10_000
```

to:

```python
DEFAULT_CHUNK_SIZE = 50_000
```

This reduces the SMS Motor Carrier Census (2.1M rows) from 210 chunk upserts to 42. Each chunk still fits comfortably in memory — at ~100 columns and ~1KB per row after metadata expansion, a 50K chunk is ~50MB of Python dicts, well within Railway container limits.

The per-feed `chunk_size` parameter in `ingest_artifact()` allows override if any specific feed needs a smaller chunk size, so this is a safe default change.

No other code changes needed — the chunking loop in `ingest_artifact()` already uses `chunk_size` dynamically.

Commit standalone.

### Deliverable 3: Delete-Then-Insert for Snapshot Feeds

Replace the ON CONFLICT upsert strategy with a delete-then-insert strategy. Since every run is a complete snapshot for a given `(feed_date, source_feed_name)`, there is no value in checking for conflicts — the new data replaces the old data entirely.

**The change is in `upsert_fmcsa_daily_diff_rows()` in `app/services/fmcsa_daily_diff_common.py`.**

Add a new parameter `use_snapshot_replace: bool = False` to `upsert_fmcsa_daily_diff_rows()`.

When `use_snapshot_replace` is `True`:

1. **Before the first chunk's temp table + COPY + merge**, execute a single DELETE statement scoped to the exact `(feed_date, source_feed_name)` being ingested:
   ```sql
   DELETE FROM entities."<table_name>"
   WHERE feed_date = <feed_date> AND source_feed_name = <source_feed_name>
   ```
   This removes all existing rows for this snapshot, so subsequent INSERTs cannot conflict.

2. **Replace the INSERT...ON CONFLICT with plain INSERT.** Since the DELETE already cleared the space, there are no conflicts to resolve. This avoids the unique index lookup on every row.

3. The DELETE + all chunk INSERTs should happen within the same transaction to maintain atomicity. This means restructuring the function so that a single connection + transaction wraps the DELETE and all chunk INSERTs, rather than acquiring/releasing per chunk.

**Important considerations:**

- The DELETE must be scoped to `(feed_date, source_feed_name)` — not a full table truncate. Other feed_dates and other feed_names must be preserved.
- `FMCSA_SNAPSHOT_HISTORY_TABLES` tables have `first_observed_at` and `last_observed_at` columns. Since we are deleting and re-inserting, `first_observed_at` will be reset to the current `source_observed_at`. This is acceptable because these are snapshot feeds — if the same `(feed_date, source_feed_name, row_position)` appears again, it is being replaced, not accumulated.
- The `record_fingerprint` column on `FMCSA_SNAPSHOT_HISTORY_TABLES` is deterministically computed from `(table_name, feed_date, feed_name, row_position)` — it will be identical on re-insert, so no data loss.

**Where to enable it:**

In `app/services/fmcsa_artifact_ingest.py`, in `ingest_artifact()`, pass `use_snapshot_replace=True` when calling `upsert_func()`. Since all 31 FMCSA feeds are snapshot feeds (each run replaces the entire `(feed_date, source_feed_name)` scope), this should be the default for all feeds.

However, to be safe, only enable it for feeds that use the `(feed_date, source_feed_name, row_position)` conflict target (which is all of them as verified). The `upsert_fmcsa_daily_diff_rows` function already determines conflict columns via `_get_conflict_columns()` — if the conflict columns are `FMCSA_CONFLICT_COLUMNS` (the standard triple), snapshot replace is safe. If legacy `record_fingerprint` conflict is detected, fall back to the existing ON CONFLICT behavior.

**Restructuring for single-transaction chunking:**

Currently `ingest_artifact()` calls `upsert_func()` per chunk, and each `upsert_func()` call acquires a connection, creates a temp table, does COPY + merge, commits, and releases. For snapshot replace, the architecture should be:

1. `ingest_artifact()` acquires a single connection at the start.
2. Executes the DELETE for the `(feed_date, source_feed_name)` scope.
3. For each chunk: creates temp table, COPY rows in, INSERT (no ON CONFLICT), commit the temp table (the temp table is `ON COMMIT DROP`). Note: since temp tables use `ON COMMIT DROP`, and we want a single wrapping transaction, change the temp table to not use `ON COMMIT DROP` — instead explicitly drop it after each chunk INSERT within the transaction.
4. After all chunks: COMMIT the transaction.
5. Release the connection.

Alternatively, keep the simpler approach: since the DELETE clears all conflicts, each chunk can still be its own transaction with `INSERT...ON CONFLICT DO NOTHING` (or plain INSERT) — the key optimization is the DELETE removing the need for Postgres to resolve conflicts. The single-transaction approach is better for atomicity but adds complexity. Use your best judgment — if single-transaction chunking is too complex, the DELETE + per-chunk plain INSERT approach still provides the majority of the performance benefit.

Commit standalone.

### Deliverable 4: Type-Check and Verify

1. Run `cd trigger && npx tsc --noEmit` to confirm no TypeScript type errors.
2. Run `pytest tests/test_fmcsa_daily_diff_persistence.py tests/test_fmcsa_artifact_ingest.py -x` to confirm Python tests pass. If tests fail because they expect `raw_values` in stored data, update them (Deliverable 1 should have caught these, but verify).
3. Verify the non-streaming path (`buildNdjsonGzipped` → `uploadArtifactAndIngest`) still compiles and its logic is correct without `raw_values`.
4. Verify that `normalizeCsvRow()` still returns a valid `FmcsaDailyDiffRow` without `raw_values`.

Commit standalone (if any fixes needed).

---

**What is NOT in scope:**

- Do not change the Trigger.dev download, parse, gzip, or TUS upload logic. The Trigger side is not the bottleneck.
- Do not change feed configurations, field mappings, cron schedules, or `normalizeCsvRow` field-mapping logic.
- Do not change the non-streaming download path (`downloadDailyDiffText` → `parseDailyDiffBody`). It works fine for small feeds.
- Do not change any FastAPI routers or API contracts. The `/api/internal/fmcsa/ingest-artifact` endpoint contract remains the same.
- Do not add new dependencies.
- Do not run deploy commands.
- Do not modify the `raw_source_row` database column itself (no migration). The column stays; it just stores less data per row.
- Do not change the Supabase Storage artifact upload/download flow.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with:
(a) For each deliverable: what changed, file paths modified, and any judgment calls made.
(b) Whether `raw_values` was fully eliminated from the codebase (excluding git history and this directive).
(c) The new chunk count for SMS Motor Carrier Census (2.1M rows) with the 50K chunk size.
(d) Whether the snapshot-replace strategy was implemented as single-transaction or per-chunk, and why.
(e) `npx tsc --noEmit` output and pytest results.
(f) Anything to flag — risks, edge cases, or concerns about the approach.
