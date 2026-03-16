**Directive: FMCSA Streaming Direct POST — Eliminate Supabase Storage Round-Trip for Streaming Feeds**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA streaming ingest pipeline for large CSV feeds (2M–13M rows) consistently OOM-kills on Trigger.dev `large-2x` machines (4 vCPU, 4 GB RAM). The root cause is the current architecture: during streaming CSV parse, rows are written to a temp NDJSON file on disk, then the file is gzipped, then the gzipped file is read entirely into memory (`readFile`), then uploaded to Supabase Storage via TUS (which copies the `Buffer`), then FastAPI downloads the artifact from Supabase Storage and processes it. For a 2.1M-row feed, the gzipped artifact is ~50-100MB, and the `readFile` + `Buffer.from()` copy exceeds the 4GB memory limit.

The fix is to eliminate the Supabase Storage round-trip entirely for streaming feeds. Instead of writing rows to a temp file → gzip → upload → download → parse → upsert, the Trigger side should POST chunks of parsed rows directly to FastAPI during the streaming CSV parse. Each feed already has a per-feed batch upsert endpoint (e.g., `/api/internal/motor-carrier-census-records/upsert-batch`) that accepts batches of `FmcsaDailyDiffRow` records. The streaming parse loop should accumulate rows in memory up to a chunk size, POST them to the feed's endpoint, clear the buffer, and repeat. This keeps Trigger-side memory at O(chunk_size × row_size) — bounded and small — regardless of total feed size.

**Recent server-side changes already deployed (version 20260314.1):**

Three server-side performance fixes are already live and relevant to this directive:

1. **`raw_values` removed from `FmcsaDailyDiffRow`.** The type is now `{ row_number: int, raw_fields: dict[str, str] }` on both sides. No `raw_values` anywhere.

2. **Snapshot replace strategy.** `upsert_fmcsa_daily_diff_rows()` in `fmcsa_daily_diff_common.py` supports `use_snapshot_replace` and `is_first_chunk` in the `FmcsaSourceContext`. When `use_snapshot_replace=True` and `is_first_chunk=True`, it executes a scoped `DELETE FROM ... WHERE feed_date = %s AND source_feed_name = %s` before the first INSERT. Subsequent chunks use plain INSERT (no ON CONFLICT). This eliminates conflict-resolution overhead for snapshot feeds.

3. **50K chunk size.** `DEFAULT_CHUNK_SIZE` in `fmcsa_artifact_ingest.py` is 50,000.

**Current architecture (what needs to change):**

`parseAndPersistStreamedCsv()` in `trigger/src/workflows/fmcsa-daily-diff.ts` (lines ~738-879) currently:

1. Creates a `WriteStream` to a temp NDJSON file on disk
2. For each CSV row: `JSON.stringify(normalizeCsvRow(...))` → write to file with backpressure
3. After all rows: closes the file stream
4. Gzips the NDJSON file via streaming pipeline with incremental SHA-256
5. `readFile(gzippedTmpPath)` — loads entire gzipped artifact into memory (**OOM here**)
6. Calls `uploadPrebuiltArtifactAndIngest()` which: uploads to Supabase Storage via TUS → POSTs manifest to `/api/internal/fmcsa/ingest-artifact` → FastAPI downloads artifact → processes chunks → confirms
7. Returns result

**Target architecture:**

`parseAndPersistStreamedCsv()` should:

1. For each CSV row: `normalizeCsvRow(...)` → push to in-memory `chunk` array
2. When `chunk.length === STREAMING_CHUNK_SIZE`: POST chunk to `feed.internalUpsertPath` → clear buffer
3. After all rows: POST remaining partial chunk
4. Return result with aggregated `rows_written` from all chunk responses

No temp file, no gzip, no Supabase Storage, no artifact download. The `InternalApiClient.post()` already gzip-compresses JSON payloads automatically via `gzipSync` (see `trigger/src/workflows/internal-api.ts` line 142).

**Existing code to read:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — the entire file, especially:
  - `FmcsaDailyDiffRow` interface (line ~71): `{ row_number: number; raw_fields: Record<string, string> }`
  - `FmcsaDailyDiffFeedConfig` interface (line ~76): note `internalUpsertPath`, `sourceFileVariant`, `writeBatchSize`
  - `FmcsaDailyDiffWorkflowResult` interface (line ~105): the return shape
  - `FmcsaDailyDiffPersistenceResponse` interface (line ~118): the shape returned by per-feed batch endpoints
  - `shouldUseStreamingParser()` (line ~182): determines which feeds use streaming
  - `normalizeCsvRow()` (line ~399): row normalization
  - `parseAndPersistStreamedCsv()` (lines ~738-879): **the function to rewrite**
  - `uploadPrebuiltArtifactAndIngest()` (lines ~640-735): used by old path, will no longer be called from streaming path
  - `runFmcsaDailyDiffWorkflow()` (line ~889): the entry point that calls `parseAndPersistStreamedCsv()`
  - `serializeSchedulePayload()`: builds `source_run_metadata`
- `trigger/src/workflows/internal-api.ts` — `InternalApiClient.post()`: gzip-compresses body, configurable timeout via `AbortSignal.timeout(timeoutMs)`
- `trigger/src/workflows/persistence.ts` — `writeDedicatedTableConfirmed()` / `confirmedInternalWrite()`: validated POST with confirmation
- `app/routers/internal.py` — per-feed batch endpoints and request models:
  - `InternalFmcsaDailyDiffRow` (line ~308): `{ row_number: int, raw_fields: dict[str, str] }`
  - `InternalUpsertFmcsaDailyDiffBatchRequest` (line ~313): includes `feed_name, feed_date, download_url, source_file_variant, source_observed_at, source_task_id, source_schedule_id, source_run_metadata, records`
  - `_build_fmcsa_source_context()` (line ~457): builds `FmcsaSourceContext` from the request
  - All 18 per-feed batch endpoints (lines ~800+): each accepts `InternalUpsertFmcsaDailyDiffBatchRequest` and calls its `upsert_func(source_context, rows)`
- `app/services/fmcsa_daily_diff_common.py` — `FmcsaSourceContext` TypedDict (has `use_snapshot_replace` and `is_first_chunk`), `upsert_fmcsa_daily_diff_rows()`
- `app/services/fmcsa_artifact_ingest.py` — artifact-based ingest (stays unchanged, used by non-streaming path)
- `trigger/src/workflows/__tests__/fmcsa-artifact-ingest.test.ts` — existing tests

---

### Deliverable 1: Add `use_snapshot_replace` and `is_first_chunk` to Batch Request Model

The per-feed batch upsert endpoints currently accept `InternalUpsertFmcsaDailyDiffBatchRequest` which does not include `use_snapshot_replace` or `is_first_chunk`. The server-side `upsert_fmcsa_daily_diff_rows()` already reads these from `FmcsaSourceContext`. The batch endpoints need to thread them through.

**Python changes in `app/routers/internal.py`:**

- Add two optional fields to `InternalUpsertFmcsaDailyDiffBatchRequest`:
  - `use_snapshot_replace: bool = False`
  - `is_first_chunk: bool = False`

- Update `_build_fmcsa_source_context()` to include these fields in the returned dict:
  - `"use_snapshot_replace": payload.use_snapshot_replace`
  - `"is_first_chunk": payload.is_first_chunk`

No other Python changes needed. The per-feed batch endpoints already call `upsert_func(source_context=_build_fmcsa_source_context(payload), rows=...)`, and the upsert function already reads `source_context.get("use_snapshot_replace", False)` and `source_context.get("is_first_chunk", False)`.

Commit standalone.

### Deliverable 2: Rewrite `parseAndPersistStreamedCsv()` to POST Chunks Directly

Replace the temp-file → gzip → Supabase Storage → artifact download flow with direct chunked HTTP POSTs to FastAPI during the streaming CSV parse.

**Function signature change:**

`parseAndPersistStreamedCsv()` currently accepts `storage: SupabaseStorageClient` as its second parameter. Remove this parameter — it is no longer needed for the streaming path.

Update the call site in `runFmcsaDailyDiffWorkflow()` accordingly.

**Add a constant for the direct POST chunk size:**

```typescript
const STREAMING_DIRECT_POST_CHUNK_SIZE = 10_000;
```

Use `feed.writeBatchSize ?? STREAMING_DIRECT_POST_CHUNK_SIZE` to allow per-feed override via the existing `writeBatchSize` config field.

10,000 rows is the right default. At ~43 columns and ~500 bytes per row of JSON, each chunk payload is ~5MB of JSON, which `gzipSync` compresses to ~1MB. This keeps Trigger-side memory at ~5-10MB per chunk (JSON string + gzip buffer + row array), well within the 4GB machine limit. For 2.1M rows, this means 210 sequential POSTs, each completing in a few seconds.

**Rewritten function logic:**

1. Set up the CSV stream parser exactly as today (same `createCsvStreamParser` options, same `inputStream.pipe(parser)`, same header validation).

2. Initialize tracking state:
   - `chunk: FmcsaDailyDiffRow[] = []`
   - `chunksProcessed = 0`
   - `totalRowsWritten = 0`
   - `chunkSize = feed.writeBatchSize ?? STREAMING_DIRECT_POST_CHUNK_SIZE`
   - Determine `useSnapshotReplace`: true for all streaming feeds (they are all complete snapshots per `(feed_date, source_feed_name)`)

3. For each CSV record from the parser:
   - Same header validation as today
   - `normalizeCsvRow(...)` → push to `chunk`
   - Increment row counters
   - When `chunk.length === chunkSize`:
     - Build the batch request payload (see below)
     - POST via `writeDedicatedTableConfirmed<FmcsaDailyDiffPersistenceResponse>()` to `feed.internalUpsertPath`
     - Aggregate `result.rows_written` into `totalRowsWritten`
     - Increment `chunksProcessed`
     - Clear `chunk = []`
   - Progress logging every 500,000 rows (same as today)

4. After the parse loop: flush the remaining partial chunk (if non-empty) with the same POST logic.

5. Same post-parse validation as today (header must have been validated, must have data rows).

6. Return `FmcsaDailyDiffWorkflowResult` with `rows_written: totalRowsWritten`.

**Building the batch request payload:**

Each POST sends a JSON body matching `InternalUpsertFmcsaDailyDiffBatchRequest`:

```typescript
{
  feed_name: payload.feed.feedName,
  feed_date: feedDate,
  download_url: payload.feed.downloadUrl,
  source_file_variant: payload.feed.sourceFileVariant,
  source_observed_at: observedAt,
  source_task_id: payload.feed.taskId,
  source_schedule_id: payload.schedule?.scheduleId ?? null,
  source_run_metadata: serializeSchedulePayload(payload.schedule, payload.feed, feedDate, observedAt),
  records: chunk,
  use_snapshot_replace: useSnapshotReplace,
  is_first_chunk: chunksProcessed === 0,
}
```

Critical: `is_first_chunk` must be `true` only for the very first chunk (when `chunksProcessed === 0`). This triggers the scoped DELETE on the server side. All subsequent chunks must send `is_first_chunk: false`.

**POST timeout:**

Each chunk POST should use a generous timeout. Use `feed.persistenceTimeoutMs ?? 300_000` (5 minutes). This matches the existing `FMCSA_LONG_RUNNING_STREAM_TIMEOUTS.persistenceTimeoutMs` default.

**POST confirmation validation:**

Use `writeDedicatedTableConfirmed` with a validate function that checks:
- `typeof response.rows_written === "number"`
- `response.rows_written >= 0`

This matches the existing pattern used by `uploadPrebuiltArtifactAndIngest`.

**Error handling:**

If any chunk POST fails, the error should propagate immediately (same as current behavior where `writeDedicatedTableConfirmed` throws `PersistenceConfirmationError`). The error message should include the chunk number and row range for debuggability.

Wrap the chunk POST in a try/catch that adds context:
```
`${feed.feedName} chunk ${chunkNumber} failed (rows ${startRow}-${endRow}): ${error.message}`
```

**What to remove from this function:**

- All temp file logic: `ndjsonTmpPath`, `ndjsonFileStream`, `createWriteStream`, file stream write loop, backpressure drain handling, file stream close/flush
- All gzip logic: `gzippedTmpPath`, `createGzip()`, `hashPassthrough`, `createHash`, pipeline, checksum
- `readFile` call
- `cleanupTmpFile` calls
- Call to `uploadPrebuiltArtifactAndIngest()`
- The `storage` parameter

**What to keep unchanged:**

- CSV stream parser setup (`createCsvStreamParser`, `Readable.fromWeb`, `inputStream.pipe(parser)`)
- Header validation logic
- `normalizeCsvRow()` call
- Row counter tracking
- Post-parse validation (header validated, has data rows)
- Progress logging every 500,000 rows
- Return shape (`FmcsaDailyDiffWorkflowResult`)

**Imports that can be removed from the function (if no longer used elsewhere in the file):**

- `createWriteStream`, `createReadStream`, `unlinkSync` from `node:fs` (check if used by non-streaming path)
- `createGzip` from `node:zlib` (check if used by non-streaming path)
- `createHash` from `node:crypto` (check if used by non-streaming path)
- `pipeline` from `node:stream/promises` (check if used by non-streaming path)
- `Transform` from `node:stream` (check if used by non-streaming path)
- `tmpdir` from `node:os` (check if used by non-streaming path)
- `join` from `node:path` (check if used by non-streaming path)

**Important:** Do NOT remove imports that are still used by the non-streaming path (`buildNdjsonGzipped()` → `uploadPrebuiltArtifactAndIngest()`). Only remove imports that are exclusively used by the old streaming path. Check each import before removing.

Commit standalone.

### Deliverable 3: Update `runFmcsaDailyDiffWorkflow()` Call Site

In `runFmcsaDailyDiffWorkflow()` (the main entry point), the streaming path currently calls:

```typescript
return parseAndPersistStreamedCsv(client, storage, payload, feedDate, observedAt, response);
```

Update this call to remove the `storage` parameter:

```typescript
return parseAndPersistStreamedCsv(client, payload, feedDate, observedAt, response);
```

If `storage` is still needed for the non-streaming path (it is — `uploadPrebuiltArtifactAndIngest` uses it), keep the `storage` variable creation in `runFmcsaDailyDiffWorkflow()` but only pass it to the non-streaming branch.

Verify that the non-streaming path (`buildNdjsonGzipped` → `uploadPrebuiltArtifactAndIngest`) still compiles and works unchanged. Do not modify it.

Commit with Deliverable 2 (same commit is fine since they are tightly coupled).

### Deliverable 4: Type-Check, Test, and Verify

1. Run `cd trigger && npx tsc --noEmit` to confirm no TypeScript type errors.
2. Run `pytest tests/test_fmcsa_daily_diff_persistence.py tests/test_fmcsa_artifact_ingest.py -x` to confirm Python tests pass.
3. Run TypeScript tests: `cd trigger && npx vitest run src/workflows/__tests__/fmcsa-artifact-ingest.test.ts` (or equivalent test runner).
4. Verify `parseAndPersistStreamedCsv` no longer references temp files, gzip, Supabase Storage, or `readFile`.
5. Verify the non-streaming path (`buildNdjsonGzipped` → `uploadPrebuiltArtifactAndIngest`) still compiles unchanged.
6. Verify that `normalizeCsvRow()` output flows correctly into the batch POST payload (the `FmcsaDailyDiffRow` type should match `InternalFmcsaDailyDiffRow` shape: `{ row_number, raw_fields }`).

Commit standalone (if any fixes needed).

---

**What is NOT in scope:**

- Do not change the non-streaming path (`buildNdjsonGzipped` → `uploadPrebuiltArtifactAndIngest`). It works for small feeds and must remain intact.
- Do not change `normalizeCsvRow()`, field mappings, or CSV parsing logic.
- Do not change feed configurations, cron schedules, or machine sizes.
- Do not change the artifact-based ingest endpoint (`/api/internal/fmcsa/ingest-artifact`) or `fmcsa_artifact_ingest.py`.
- Do not change any per-feed row builders or `upsert_fmcsa_daily_diff_rows()` logic.
- Do not change `InternalApiClient` or `confirmedInternalWrite`.
- Do not add new dependencies.
- Do not run deploy commands.
- Do not re-enable any disabled crons.
- Do not change `shouldUseStreamingParser()` logic.
- Do not modify `DEFAULT_CHUNK_SIZE` in `fmcsa_artifact_ingest.py` (that is for the artifact path, not the direct POST path).

**Commit convention:** Each deliverable is one commit. Deliverables 2 and 3 may share a commit since they are tightly coupled. Do not push.

**When done:** Report back with:
(a) For each deliverable: what changed, file paths modified, and any judgment calls made.
(b) The new memory profile for streaming feeds: what is the peak memory usage per chunk at 10K rows × 43 columns? Confirm it is well within 4GB.
(c) How many HTTP POSTs the SMS Motor Carrier Census (2.1M rows) will make with the 10K default chunk size.
(d) Whether `is_first_chunk` is correctly set to `true` only for the very first chunk and `false` for all subsequent chunks.
(e) Whether the non-streaming path still compiles and works unchanged.
(f) `npx tsc --noEmit` output and pytest / vitest results.
(g) Anything to flag — risks, edge cases, or concerns about the approach.
