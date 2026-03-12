# Directive: FMCSA Persistence Phase Instrumentation and Connection Pooling

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA bulk ingestion pipeline is timing out on the heaviest feeds (`Company Census File` at 4.4M rows, `Vehicle Inspection File` at 8.2M rows). The performance diagnosis (`docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`) measured that non-DB CPU per 10K wide batch is roughly `4s`, but production batch round-trips are `40–300s`. The dominant cost is server-side persistence, but we do not know the exact split between connection acquisition, temp-table creation, COPY into staging, merge into the canonical table, and commit. That split is currently inferred from code shape, not measured. This directive adds explicit phase timing so we can see production numbers, and replaces the per-batch connection open with a pooled or reusable connection to eliminate the connection-setup tax across hundreds of batches per feed.

**What this directive does NOT address:** Request body compression is handled by a separate directive. Do not modify `trigger/src/workflows/internal-api.ts` or add middleware to `app/main.py`.

**Existing code to read:**

- `CLAUDE.md`
- `docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md` — bottleneck analysis, phase cost estimates, and the connection-reuse recommendation
- `app/services/fmcsa_daily_diff_common.py` — the `upsert_fmcsa_daily_diff_rows()` function and `get_fmcsa_direct_postgres_connection()`
- `app/config.py` — `get_settings()` and `database_url`
- `app/routers/internal.py` — the 18 FMCSA `upsert-batch` endpoint handlers that call the per-feed service functions
- One representative per-feed service file (e.g., `app/services/motor_carrier_census_records.py`) to see how `upsert_fmcsa_daily_diff_rows` is called

---

### Deliverable 1: Phase Instrumentation in `upsert_fmcsa_daily_diff_rows`

Add explicit timing instrumentation inside the `upsert_fmcsa_daily_diff_rows()` function in `app/services/fmcsa_daily_diff_common.py`.

Requirements:

- Use `time.perf_counter()` to measure each phase. Phases to time:
  1. **request_body_rows**: number of rows received (not a timer — just capture `len(rows)` for log correlation)
  2. **row_builder_ms**: time spent in the row-builder loop (iterating `rows`, calling `row_builder()`, assembling `upsert_rows`)
  3. **connection_acquire_ms**: time to acquire the Postgres connection (from the call to get/checkout a connection until a usable connection object is in hand)
  4. **temp_table_create_ms**: time for `_create_temp_staging_table()`
  5. **copy_ms**: time for `_copy_rows_into_temp_table()`
  6. **merge_ms**: time for `cursor.execute(upsert_sql)` (the INSERT...ON CONFLICT merge)
  7. **commit_ms**: time for `connection.commit()`
  8. **total_ms**: wall time from function entry to return

- After the persistence completes (success or failure), emit a single structured log line with all phase timings. Use Python's `logging` module at `INFO` level. The log message should be a short label like `"fmcsa_batch_persist_phases"` with the phase timings and context as structured fields. Include `table_name`, `feed_date`, `rows_received`, and `rows_written` alongside the timings.

- Example log shape (you choose the exact format, but it must contain all these fields):
  ```
  fmcsa_batch_persist_phases table=motor_carrier_census_records feed_date=2026-03-12 rows=10000 row_builder_ms=374 conn_acquire_ms=45 temp_table_ms=12 copy_ms=890 merge_ms=28400 commit_ms=120 total_ms=29900
  ```

- On failure (exception), still log whatever phases completed before the failure, plus an `error=true` flag. Then re-raise the exception. Do not swallow errors.

- Do not change the function signature, return type, or the caller contract. The per-feed service files and the router endpoints must not need any changes.

- Do not add new pip dependencies. `time` and `logging` are stdlib.

Commit standalone.

### Deliverable 2: Connection Pooling for FMCSA Bulk Writes

Replace the per-call `connect(settings.database_url)` in the FMCSA write path with a connection pool that reuses connections across batch writes within the same FastAPI process.

Requirements:

- Replace the current `get_fmcsa_direct_postgres_connection()` function. The current implementation opens a fresh `psycopg.connect()` on every call. With 441 batches for Company Census, that is 441 connection setups.

- Use `psycopg_pool.ConnectionPool` (from the `psycopg_pool` package, which is the official psycopg3 pooling library). If `psycopg_pool` is not already in `requirements.txt`, add it.

- Create a module-level pool singleton in `app/services/fmcsa_daily_diff_common.py` (or a small dedicated helper if cleaner). The pool should:
  - Be lazily initialized on first use.
  - Have a `min_size` of `1` and a `max_size` of `4`. These are FMCSA-only connections, not the app's general pool. `4` is sufficient since FMCSA feeds currently run at concurrency `1`, but allows headroom for future light parallelism without overwhelming Postgres.
  - Use the same `settings.database_url` from `app.config.get_settings()`.
  - Have a connection `timeout` of `30` seconds (time waiting for a free connection from the pool).

- Update `upsert_fmcsa_daily_diff_rows()` to acquire a connection from the pool instead of opening a new one. Use the pool's context manager for checkout/checkin so connections are always returned, even on failure.

- The `_get_table_columns()` function also calls `get_fmcsa_direct_postgres_connection()`. Update it to use the same pool.

- Do not change the per-feed service files or the router endpoint handlers. The pool is internal to the common module.

- Do not create a global app-wide connection pool. This pool is scoped to the FMCSA bulk write path only.

- Ensure the pool handles connection health. `psycopg_pool.ConnectionPool` has built-in connection checking; rely on its defaults unless you find a reason to override.

Commit standalone.

### Deliverable 3: Tests

Add or update tests that validate the instrumentation and connection pooling.

Instrumentation tests:

- Verify that `upsert_fmcsa_daily_diff_rows()` emits a log record at INFO level containing the `fmcsa_batch_persist_phases` label (or whatever label you chose) with all required phase fields (`row_builder_ms`, `connection_acquire_ms`, `temp_table_create_ms`, `copy_ms`, `merge_ms`, `commit_ms`, `total_ms`, `table_name`, `rows_received`, `rows_written`).
- Verify that on a simulated failure, the log record is still emitted with `error=true` (or equivalent) and the exception is re-raised.
- You may mock the database connection/cursor layer to isolate these tests from a real database.

Connection pooling tests:

- Verify that two sequential calls to the pool-based connection getter return connections from the same pool (not two independent `connect()` calls).
- Verify that if `psycopg_pool` is not available (import fails), the code falls back gracefully or raises a clear error at startup. Use your judgment on whether fallback or fail-fast is better — justify in your report.

Use the existing test patterns in `tests/`. Do not require a live database for these tests.

Commit standalone.

---

**What is NOT in scope:** No changes to `trigger/src/workflows/internal-api.ts` or any Trigger-side code. No changes to `app/main.py` or FastAPI middleware. No changes to the Pydantic request/response models. No changes to the FMCSA endpoint handler signatures in `app/routers/internal.py`. No changes to non-FMCSA services or the general app database layer. No batch size changes. No deploy commands. No push.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the exact log format chosen and a sample log line, (b) how phase timing is captured (perf_counter pairs, context managers, etc.), (c) how the failure-path logging works, (d) the connection pool configuration (`min_size`, `max_size`, `timeout`, lazy init strategy), (e) whether `psycopg_pool` was already a dependency or was added, (f) how `_get_table_columns()` was updated, (g) test count and what each test proves, (h) anything to flag — especially if you found that `psycopg_pool` has compatibility issues with the current `psycopg` version or if the `lru_cache` on `_get_table_columns` interacts poorly with pooled connections.
