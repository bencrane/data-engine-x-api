# Directive: FMCSA Staged Artifact Ingest

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA bulk ingestion pipeline currently sends parsed rows from Trigger.dev to FastAPI as JSON-over-HTTP in sequential batches. For the heaviest feeds (`Company Census File` at 4.4M rows, `Vehicle Inspection File` at 8.2M rows), this means 441+ sequential confirmed HTTP round trips, each carrying up to 35 MB of JSON (now gzip-compressed to ~2.3 MB). Production batch round-trips are 40–300s, dominated by server-side persistence time. Even with the recently deployed gzip compression and connection pooling, the fundamental problem remains: the architecture is too chatty. The performance diagnosis (`docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`) identifies "staged artifact + FastAPI ingest by reference" as the best architectural option that stays within the current FastAPI/Trigger ownership boundary. This directive replaces the batch-by-batch HTTP loop with a single artifact upload + manifest confirmation pattern for all 31 FMCSA feeds.

**What this directive does NOT address:** The old per-batch HTTP upsert endpoints in `app/routers/internal.py` are not removed in this directive. They become dead code once this work ships. A follow-up directive will remove them. Do not remove them here.

**Existing code to read:**

- `CLAUDE.md`
- `docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md` — bottleneck analysis, architectural alternatives, and the staged artifact recommendation
- `trigger/src/workflows/fmcsa-daily-diff.ts` — the current Trigger-side ingestion workflow with batch loop and streaming parser
- `trigger/src/workflows/internal-api.ts` — the `InternalApiClient` and `InternalApiClient.post()` method
- `trigger/src/workflows/persistence.ts` — `writeDedicatedTableConfirmed()` and `confirmedInternalWrite()` wrappers
- `app/services/fmcsa_daily_diff_common.py` — the current persistence layer: row builder, column projection, temp table COPY, merge SQL, phase instrumentation, connection pool
- `app/routers/internal.py` — the 18 FMCSA `upsert-batch` endpoint handlers and `InternalUpsertFmcsaDailyDiffBatchRequest` model
- `app/config.py` — `get_settings()`, `supabase_url`, `supabase_service_key`, `database_url`
- `app/database.py` — `get_supabase_client()` and the raw Supabase client setup
- `requirements.txt` — current Python dependencies
- `trigger/package.json` — current npm dependencies
- One representative per-feed service file (e.g., `app/services/motor_carrier_census_records.py`) to see how `upsert_fmcsa_daily_diff_rows` is called and what a `row_builder` looks like

---

### Deliverable 1: Trigger-Side Artifact Upload

Replace the batch-by-batch HTTP persistence loop in `trigger/src/workflows/fmcsa-daily-diff.ts` with artifact upload to Supabase Storage followed by a single manifest POST.

Requirements:

- After downloading and parsing the CSV (the download/parse logic stays the same), instead of calling `persistDailyDiffRows()` in a batch loop, write all parsed rows as gzipped NDJSON to a Supabase Storage bucket. Each line of the NDJSON file is one row in the existing `FmcsaDailyDiffRow` shape: `{"row_number": <int>, "raw_values": [<string>, ...], "raw_fields": {"field": "value", ...}}`.

- Use a dedicated Supabase Storage bucket named `fmcsa-artifacts`. The artifact object path should follow a clear naming convention that includes feed name, feed date, and a disambiguating suffix (e.g., timestamp or task run ID) to prevent collisions on reruns. Example: `{feed_name}/{feed_date}/{run_id}.ndjson.gz`. The exact convention is your choice — just make it deterministic and debuggable.

- Gzip the NDJSON content before uploading. Use Node.js built-in `zlib` for compression.

- After uploading the artifact, send FastAPI a single manifest POST to a new endpoint: `POST /api/internal/fmcsa/ingest-artifact`. The manifest payload shape:
  ```
  {
    "feed_name": string,
    "feed_date": string,
    "download_url": string,
    "source_file_variant": "daily diff" | "daily" | "all_with_history" | "csv_export",
    "source_observed_at": string,
    "source_task_id": string,
    "source_schedule_id": string | null,
    "source_run_metadata": object,
    "artifact_bucket": string,
    "artifact_path": string,
    "row_count": number,
    "artifact_checksum": string    // SHA-256 hex digest of the gzipped artifact bytes
  }
  ```

- The manifest POST uses the existing `InternalApiClient`. Add a dedicated method or use the existing `post()` method — your choice. The timeout for this request must be generous: the server side will download, decompress, parse, and persist the entire feed in one request. Use a timeout of at least `1_800_000` ms (30 minutes) for the manifest call. This is much longer than the old per-batch timeout because this single request replaces hundreds of sequential requests.

- The confirmation response from FastAPI should match this shape:
  ```
  {
    "feed_name": string,
    "table_name": string,
    "feed_date": string,
    "rows_received": number,
    "rows_written": number,
    "checksum_verified": boolean
  }
  ```
  Trigger must validate that `checksum_verified` is `true`, `rows_received` matches the uploaded row count, and `rows_written >= 0`. If validation fails, raise a `PersistenceConfirmationError`.

- After confirmed success, delete the artifact from Supabase Storage. If deletion fails, log a warning but do not fail the workflow — the artifact has served its purpose and can be cleaned up later.

- The workflow result shape (`FmcsaDailyDiffWorkflowResult`) does not change. Populate it from the manifest confirmation.

- Both the streaming parser path and the non-streaming path should use the artifact approach. The difference between them is only how rows are parsed — both paths now write an artifact instead of batch-POSTing.

- For Supabase Storage access from Trigger, you will need `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` as environment variables in the Trigger runtime. These already exist in Doppler. You may use `@supabase/supabase-js` (add it to `trigger/package.json`) or call the Supabase Storage REST API directly with `fetch` — your choice. If you add `@supabase/supabase-js`, use the latest stable version.

- Do not change the feed config shape (`FmcsaDailyDiffFeedConfig`). The `internalUpsertPath` field on each feed config becomes unused by this new path but must not be removed (follow-up directive removes it).

- The `writeBatchSize` field on feed configs is no longer used for HTTP batching, but may be repurposed by the FastAPI side for chunked processing of the artifact. Keep it on the config; the FastAPI side will decide how to use it.

Commit standalone.

### Deliverable 2: FastAPI Artifact Ingest Endpoint

Add a new FastAPI internal endpoint that receives a manifest, downloads the artifact from Supabase Storage, and ingests it through the existing persistence pipeline.

Requirements:

- Create a new file `app/services/fmcsa_artifact_ingest.py` for the artifact download and ingestion logic.

- Add a new endpoint `POST /api/internal/fmcsa/ingest-artifact` in `app/routers/internal.py`. It receives the manifest payload described in Deliverable 1. It is protected by the same `require_internal_key` auth as the existing FMCSA endpoints.

- The endpoint must:
  1. Download the artifact from Supabase Storage using the `artifact_bucket` and `artifact_path` from the manifest. Use the existing Supabase Python client (`supabase` package, already in `requirements.txt`) or direct HTTP — your choice.
  2. Verify the SHA-256 checksum of the downloaded gzipped bytes against `artifact_checksum`. If mismatch, return HTTP `422` with a clear error message. Do not proceed with ingestion on checksum failure.
  3. Decompress the gzipped artifact.
  4. Parse the NDJSON content. Each line is a `FmcsaDailyDiffRow` (`row_number`, `raw_values`, `raw_fields`).
  5. Determine which FMCSA table to write to based on `feed_name`. This is the mapping that currently lives implicitly in the 18 separate endpoint handlers and their per-feed service functions. The new endpoint must resolve `feed_name` → `(table_name, row_builder)`. Collect these mappings from the existing per-feed service modules. Create a registry dict that maps feed names to their table name and row builder function. This is the key architectural simplification: one endpoint replaces 18.
  6. Process the rows in chunked batches through the existing persistence internals. The chunk size should default to `10_000` rows (matching the current `writeBatchSize` for wide feeds). The chunked processing reuses `upsert_fmcsa_daily_diff_rows()` for each chunk — the existing function handles row building, column projection, temp table COPY, merge, and phase instrumentation. Each chunk is a separate call to `upsert_fmcsa_daily_diff_rows()`, each with its own transaction.
  7. Accumulate `rows_written` across all chunks.
  8. Return the confirmation envelope described in Deliverable 1.

- The artifact download and decompression should be streamed if practical. For a 4.4M row Company Census artifact, the gzipped NDJSON will be much smaller than 4.4M × 35 MB / 10K = 15.4 GB of raw JSON (because NDJSON is more compact per row than the nested batch envelope, and it's gzipped). But the decompressed NDJSON could still be hundreds of MB for the largest feeds. Do not buffer the entire decompressed content in memory at once — stream and parse line by line, accumulating rows into chunks.

- Build the `FmcsaSourceContext` from the manifest fields, exactly as the existing per-batch endpoints do. The source context shape does not change.

- Phase instrumentation: emit the same `fmcsa_batch_persist_phases` log per chunk (this happens automatically via `upsert_fmcsa_daily_diff_rows()`). Additionally, emit one summary log at the end of the entire artifact ingest with label `fmcsa_artifact_ingest_summary` containing: `feed_name`, `feed_date`, `table_name`, `artifact_path`, `total_rows_received`, `total_rows_written`, `chunks_processed`, `artifact_download_ms`, `artifact_decompress_parse_ms`, `total_persist_ms`, `total_ms`.

- Error handling: if any chunk fails during persistence, stop processing, log the failure with chunk number and rows processed so far, and return an error response. Do not continue to subsequent chunks after a failure. The error must be loud — return HTTP `500` with a clear message, not a fake success.

- Feed name to table/row-builder registry: the mapping between `feed_name` values and their `(table_name, row_builder)` pairs currently exists implicitly across the 18 endpoint handlers in `app/routers/internal.py` and their per-feed service modules. You need to extract this into an explicit registry. Read each of the 18 per-feed service files to find the `row_builder` function and `table_name` for each feed. The registry should be a dict or similar structure in `app/services/fmcsa_artifact_ingest.py` (or a shared location if cleaner). The feed names are the `FmcsaFeedName` values from the Trigger side — make sure the mapping uses the same string values.

- Do not modify `app/services/fmcsa_daily_diff_common.py`. The existing `upsert_fmcsa_daily_diff_rows()` function is the persistence engine — call it, do not rewrite it.

- Do not modify the existing 18 per-batch FMCSA endpoint handlers. They remain as-is (dead code after this ships, removed in follow-up).

- Do not modify the per-feed service files. Import their row builders and table names; do not move or restructure them.

Commit standalone.

### Deliverable 3: Supabase Storage Bucket Setup and Artifact TTL

Ensure the `fmcsa-artifacts` bucket exists and configure artifact cleanup.

Requirements:

- Add bucket creation logic that runs on first use (or at startup). The bucket should be created as a private bucket (not publicly accessible). If it already exists, do not fail.

- Implement artifact TTL cleanup: artifacts older than 7 days should be automatically deleted. You have two options:
  - Option A: Add a cleanup step in the Trigger workflow that deletes old artifacts for the same feed after a successful run.
  - Option B: Add a FastAPI background task or scheduled utility that lists and deletes expired artifacts.

  Choose whichever is simpler and more reliable. Document your choice in the report.

- The bucket name `fmcsa-artifacts` should be a constant, not hardcoded in multiple places.

Commit standalone.

### Deliverable 4: Tests

Add tests that validate the artifact ingest pipeline without requiring a live database or Supabase Storage.

Trigger-side tests (in `trigger/` test infrastructure):

- Verify that the workflow writes a gzipped NDJSON artifact where each line, when decompressed and parsed, matches the `FmcsaDailyDiffRow` shape.
- Verify that the manifest POST contains the correct fields including `artifact_bucket`, `artifact_path`, `row_count`, and `artifact_checksum`.
- Verify that the checksum in the manifest matches the SHA-256 of the uploaded artifact bytes.
- Verify that after confirmed success, the workflow attempts to delete the artifact.
- Use mock `fetch` and mock Supabase Storage client to isolate these tests.

FastAPI-side tests (in `tests/`):

- Verify that the `/api/internal/fmcsa/ingest-artifact` endpoint correctly processes a small NDJSON artifact (mock the Supabase Storage download to return a gzipped NDJSON buffer).
- Verify that a checksum mismatch returns HTTP `422`.
- Verify that the feed-name-to-table-and-row-builder registry covers all 18 FMCSA feeds (at minimum, check that every feed name has an entry and that the row builder is callable).
- Verify that chunked processing calls `upsert_fmcsa_daily_diff_rows()` the expected number of times for a given row count and chunk size.
- Verify that a simulated persistence failure on one chunk stops processing and returns an error (not a fake success with partial data).
- Mock the database connection/cursor layer. Do not require a live database.

Commit standalone.

---

**What is NOT in scope:** No removal of the existing 18 per-batch FMCSA upsert endpoints (follow-up). No changes to `app/services/fmcsa_daily_diff_common.py` (the persistence engine). No changes to the per-feed service files (row builders stay where they are). No changes to the Pydantic request/response models for the old batch endpoints. No changes to non-FMCSA services or the general app database layer. No batch size tuning. No schema migrations. No deploy commands. No push.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) how the Trigger-side artifact upload works (Supabase client choice, compression approach, artifact path convention, NDJSON line format), (b) how the manifest POST and confirmation validation work, (c) the manifest timeout value chosen and rationale, (d) how the FastAPI artifact ingest endpoint works (download, checksum verification, streaming decompression, chunked persistence), (e) the complete feed-name-to-table-and-row-builder registry (all 18+ entries), (f) how chunk size is determined, (g) the artifact cleanup/TTL strategy chosen and why, (h) how errors are surfaced (checksum mismatch, download failure, persistence failure mid-artifact), (i) test count and what each test proves, (j) whether `@supabase/supabase-js` was added or whether raw REST was used on the Trigger side, (k) anything to flag — especially if you discovered that Supabase Storage has upload size limits that would be hit by the largest feeds, or if streaming download from Supabase Storage is not well-supported by the Python client.
