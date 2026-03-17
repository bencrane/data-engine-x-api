**Directive: Migrate `parseAndPersistStreamedCsv` from Artifact Storage Round-Trip to Direct Chunk POST**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** All streaming CSV feeds (SMS feeds, Crash File, Inspections Per Unit, Vehicle Inspections and Violations, Company Census File, Vehicle Inspection File) route through `parseAndPersistStreamedCsv()` which currently does a Supabase Storage round-trip per chunk: gzip rows → upload to Storage → POST manifest to `/api/internal/fmcsa/ingest-artifact` → FastAPI downloads from Storage → decompresses → parses NDJSON → persists. This round-trip is failing for large feeds — Supabase Storage file size limits, TUS upload OOM, and unnecessary latency. The per-table `/api/internal/*/upsert-batch` endpoints already support `use_snapshot_replace` and `is_first_chunk` fields and use the same COPY+merge persistence path. The fix is to POST chunks directly to those endpoints during the streaming CSV parse, eliminating Storage entirely from the streaming path.

**What already works and must not change:**

- The non-streaming artifact path (small daily-diff feeds that go through `uploadArtifactAndIngest`) — this stays exactly as-is.
- The streaming CSV download and parse logic (`createCsvStreamParser`, `Readable.fromWeb`, header validation, `normalizeCsvRow`).
- The Python persistence layer (`upsert_fmcsa_daily_diff_rows`, per-feed upsert functions, COPY+merge internals).
- The per-table batch endpoint request model `InternalUpsertFmcsaDailyDiffBatchRequest` which already has `use_snapshot_replace: bool = False` and `is_first_chunk: bool = False`.
- `_build_fmcsa_source_context()` which already threads both fields through to `FmcsaSourceContext`.

**Existing code to read:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — the entire file, especially:
  - `FmcsaDailyDiffRow` interface (line ~67): `{ row_number: number; raw_fields: Record<string, string> }`
  - `FmcsaDailyDiffFeedConfig` interface (line ~72): note `internalUpsertPath`, `writeBatchSize`, `persistenceTimeoutMs`
  - `FmcsaDailyDiffWorkflowResult` interface (line ~101): the return shape
  - `FmcsaArtifactIngestConfirmation` interface (line ~114): current confirmation shape (will be replaced)
  - `STREAMING_DIRECT_POST_CHUNK_SIZE` constant (line ~729): `10_000`
  - `MANIFEST_INGEST_TIMEOUT_MS` constant (line ~152): `1_800_000` (30 minutes)
  - `parseAndPersistStreamedCsv()` (lines ~731-912): **the function to change**
  - `runFmcsaDailyDiffWorkflow()` (line ~914): calls `parseAndPersistStreamedCsv` — the call site to update
  - `serializeSchedulePayload()`: builds `source_run_metadata`
  - `buildNdjsonGzipped()` (line ~532): used by current flushChunk — will no longer be called from streaming path
  - `shouldUseStreamingParser()` (line ~173): determines which feeds use streaming
- `trigger/src/workflows/internal-api.ts` — `InternalApiClient.post()`: automatically gzip-compresses JSON payloads via `gzipSync` (line ~142), configurable timeout via `AbortSignal.timeout(timeoutMs)`
- `trigger/src/workflows/persistence.ts` — `writeDedicatedTableConfirmed()`: validated POST with confirmation envelope unwrapping
- `app/routers/internal.py`:
  - `InternalFmcsaDailyDiffRow` (line ~308): `{ row_number: int, raw_fields: dict[str, str] }`
  - `InternalUpsertFmcsaDailyDiffBatchRequest` (line ~313): includes `feed_name`, `feed_date`, `download_url`, `source_file_variant`, `source_observed_at`, `source_task_id`, `source_schedule_id`, `source_run_metadata`, `records`, `use_snapshot_replace`, `is_first_chunk`
  - `_build_fmcsa_source_context()` (line ~461): builds `FmcsaSourceContext` from the request, already includes `use_snapshot_replace` and `is_first_chunk`
  - Per-table batch endpoints (lines ~808+): each accepts `InternalUpsertFmcsaDailyDiffBatchRequest` and returns `{ feed_name, table_name, feed_date, rows_received, rows_written }` wrapped in `DataEnvelope`
- `app/services/fmcsa_daily_diff_common.py`:
  - `upsert_fmcsa_daily_diff_rows()` (line ~375): returns `{ feed_name, table_name, feed_date, rows_received, rows_written }`
  - Snapshot-replace logic (line ~487): when `use_snapshot_replace=True` and `is_first_chunk=True`, executes scoped `DELETE FROM ... WHERE feed_date = %s AND source_feed_name = %s` before INSERT

---

### Deliverable 1: Rewrite `flushChunk` in `parseAndPersistStreamedCsv()` to POST Directly to Per-Table Endpoints

Replace the Supabase Storage artifact upload + manifest flow in `flushChunk` with a direct POST to `feed.internalUpsertPath`.

**Current `flushChunk` flow (to be replaced):**

1. `buildNdjsonGzipped(chunk)` — serialize rows to NDJSON, gzip
2. `storage.upload(...)` — upload gzipped artifact to Supabase Storage
3. Build `FmcsaArtifactIngestManifest` with `artifact_bucket`, `artifact_path`, `artifact_checksum`
4. `writeDedicatedTableConfirmed(...)` to `/api/internal/fmcsa/ingest-artifact`
5. FastAPI downloads from Storage → decompresses → parses NDJSON → persists
6. Delete artifact from Storage after confirmation

**New `flushChunk` flow:**

1. Build a batch request payload matching `InternalUpsertFmcsaDailyDiffBatchRequest`:

   ```typescript
   {
     feed_name: payload.feed.feedName,
     feed_date: feedDate,
     download_url: payload.feed.downloadUrl,
     source_file_variant: payload.feed.sourceFileVariant,
     source_observed_at: observedAt,
     source_task_id: payload.feed.taskId,
     source_schedule_id: payload.schedule?.scheduleId ?? null,
     source_run_metadata: sourceRunMetadata,
     records: chunk,
     use_snapshot_replace: true,
     is_first_chunk: chunksProcessed === 0,
   }
   ```

2. POST via `writeDedicatedTableConfirmed` to `payload.feed.internalUpsertPath` (e.g., `/api/internal/motor-carrier-census-records/upsert-batch`). The `InternalApiClient.post()` automatically gzip-compresses the JSON payload — no manual gzip needed.

3. Validate the response:

   ```typescript
   validate: (response) =>
     isRecord(response) &&
     typeof response.rows_written === "number" &&
     response.rows_written >= 0,
   ```

   Note: the per-table endpoints return `{ feed_name, table_name, feed_date, rows_received, rows_written }`. The confirmation type should match this shape (not the old `FmcsaArtifactIngestConfirmation` with `checksum_verified`).

4. Aggregate `response.rows_written` into `totalRowsWritten`.

**Timeout:** Use `payload.feed.persistenceTimeoutMs ?? 300_000` (5 minutes per chunk). Do NOT use `MANIFEST_INGEST_TIMEOUT_MS` (30 minutes) — that was for the artifact path where FastAPI had to download + decompress + process the entire artifact. Direct POST chunks are much faster.

**`is_first_chunk` correctness:** Must be `true` only when `chunksProcessed === 0`. This triggers the scoped DELETE on the server side. All subsequent chunks must send `false`. This is already the logic in the current code — preserve it.

**Error handling:** Keep the existing try/catch that wraps errors with chunk number and row range context. The error message format `${feed.feedName} chunk ${chunkNumber} failed (rows ${startRow}-${endRow}): ${error.message}` should remain.

**Logging:** Keep the existing `logger.info("fmcsa streaming chunk upload", ...)` log line, but rename it to something like `"fmcsa streaming chunk post"` and remove the `artifact_size_bytes` field (no artifact anymore). Add `endpoint: payload.feed.internalUpsertPath` for debuggability.

**What to remove from `flushChunk`:**

- `buildNdjsonGzipped(chunk)` call
- `resolveArtifactPath(...)` call
- `storage.upload(...)` call
- `FmcsaArtifactIngestManifest` construction
- The POST to `/api/internal/fmcsa/ingest-artifact`
- The post-confirmation `storage.remove(...)` cleanup

**What to remove from `parseAndPersistStreamedCsv` outside of `flushChunk`:**

- `await ensureBucketExists(storage)` call (line ~765)
- `await cleanupOldArtifacts(storage, payload.feed)` call (line ~891)
- The `storage` parameter from the function signature

**What to keep unchanged in `parseAndPersistStreamedCsv`:**

- CSV stream parser setup (`createCsvStreamParser`, `Readable.fromWeb`, `inputStream.pipe(parser)`)
- Header validation logic
- `normalizeCsvRow()` call
- Row counter tracking (`rowNumber`, `rowsDownloaded`, `rowsParsed`, `rowsAccepted`)
- Chunk size resolution: `payload.feed.writeBatchSize ?? STREAMING_DIRECT_POST_CHUNK_SIZE`
- The `for await (const record of parser)` loop structure
- Post-parse validation (header validated, has data rows)
- Progress logging every 500,000 rows
- Final partial chunk flush
- Return shape (`FmcsaDailyDiffWorkflowResult`)
- The `try { ... } catch (error) { throw formatStreamingWorkflowError(...) }` wrapper

Commit standalone.

---

### Deliverable 2: Update `runFmcsaDailyDiffWorkflow()` Call Site

In `runFmcsaDailyDiffWorkflow()` (line ~914), the streaming branch currently calls:

```typescript
const result = await parseAndPersistStreamedCsv(
  client,
  storage,
  payload,
  feedDate,
  observedAt,
  response,
);
```

Remove the `storage` argument:

```typescript
const result = await parseAndPersistStreamedCsv(
  client,
  payload,
  feedDate,
  observedAt,
  response,
);
```

The `storage` variable and `createStorageClient(dependencies)` call must remain in `runFmcsaDailyDiffWorkflow()` because the non-streaming branch still uses them (`uploadArtifactAndIngest` calls `storage.upload`). Only the streaming branch stops passing `storage`.

Verify that the non-streaming path (`downloadDailyDiffText` → `parseDailyDiffBody` → `uploadArtifactAndIngest`) still compiles and works unchanged.

Commit with Deliverable 1 (same commit — they are tightly coupled).

---

### Deliverable 3: Add a Response Type for Per-Table Batch Endpoint

The current `FmcsaArtifactIngestConfirmation` type has `checksum_verified` which is artifact-specific. Add (or repurpose) a response type matching the per-table endpoint return shape:

```typescript
interface FmcsaBatchUpsertResponse {
  feed_name: string;
  table_name: string;
  feed_date: string;
  rows_received: number;
  rows_written: number;
}
```

Use this type in the `writeDedicatedTableConfirmed<FmcsaBatchUpsertResponse>(...)` call inside `flushChunk`.

Do NOT remove `FmcsaArtifactIngestConfirmation` — it is still used by the non-streaming artifact path.

Commit with Deliverable 1 if convenient.

---

### Deliverable 4: Verify and Test

1. Run `cd trigger && npx tsc --noEmit` to confirm no TypeScript type errors.
2. Run `doppler run -- pytest tests/test_fmcsa_daily_diff_persistence.py tests/test_fmcsa_artifact_ingest.py -x` to confirm Python tests still pass (Python code is not modified, but verify nothing is broken).
3. If there are existing TypeScript tests for the streaming path (`trigger/src/workflows/__tests__/`), run them and fix any failures caused by the signature change.
4. Verify that `parseAndPersistStreamedCsv` no longer references `storage`, `buildNdjsonGzipped`, `ensureBucketExists`, `cleanupOldArtifacts`, `resolveArtifactPath`, `FmcsaArtifactIngestManifest`, or `MANIFEST_INGEST_TIMEOUT_MS`.
5. Verify that the non-streaming path (`uploadArtifactAndIngest` → `uploadPrebuiltArtifactAndIngest`) still compiles and references `storage` correctly.
6. Verify that `is_first_chunk` is `true` only for the first chunk (`chunksProcessed === 0`) and `false` for all subsequent chunks.

Commit standalone (if any fixes needed).

---

**What is NOT in scope:**

- Do not change the non-streaming path (`parseDailyDiffBody` → `uploadArtifactAndIngest`). It works for small daily-diff feeds and must remain intact.
- Do not change `normalizeCsvRow()`, field mappings, header validation, or CSV parsing logic.
- Do not change feed configurations, cron schedules, `writeBatchSize` values, or machine sizes.
- Do not change the artifact-based ingest endpoint (`/api/internal/fmcsa/ingest-artifact`) or `app/services/fmcsa_artifact_ingest.py`.
- Do not change any per-feed row builders, `upsert_fmcsa_daily_diff_rows()`, or any Python code.
- Do not change `InternalApiClient`, `writeDedicatedTableConfirmed`, or `confirmedInternalWrite`.
- Do not change `shouldUseStreamingParser()` logic.
- Do not change `InternalUpsertFmcsaDailyDiffBatchRequest` or `_build_fmcsa_source_context()` — they already have the needed fields.
- Do not add new dependencies.
- Do not run deploy commands.
- Do not remove imports that are still used by the non-streaming path. Check each import before removing.

**Commit convention:** Deliverables 1, 2, and 3 may share a single commit since they are tightly coupled. Deliverable 4 is a separate commit if fixes are needed. Do not push.

**When done:** Report back with:
(a) What changed in `flushChunk`: the old flow vs new flow, confirming Storage is fully eliminated.
(b) The per-chunk memory profile: at 10K rows × ~40 columns, what is the approximate JSON payload size before gzip? Confirm this is well within machine memory limits.
(c) How many HTTP POSTs the Company Census File (4.4M rows, 147 columns, `writeBatchSize: 10000`) will make with the 10K chunk size.
(d) Whether `is_first_chunk` is correctly `true` only for the first chunk and `false` for all subsequent chunks.
(e) Whether the non-streaming path still compiles and works unchanged.
(f) `npx tsc --noEmit` output and pytest results.
(g) Any imports removed and confirmation they were not used by the non-streaming path.
(h) Anything to flag — risks, edge cases, or concerns.
