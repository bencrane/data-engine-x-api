**Directive: FMCSA Streaming Artifact Performance — Eliminate Buffering and Backpressure Bottlenecks**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA staged artifact ingest pipeline downloads CSV feeds from data.transportation.gov, converts them to gzipped NDJSON artifacts, uploads to Supabase Storage, and sends a manifest POST so FastAPI can download and persist the data. Small feeds (< 50K rows) complete fine. Large feeds (1M–13M rows) fail with OOM or take 37+ minutes on the Trigger side. The root cause is that the current streaming parse loop writes NDJSON lines to a temp file using `createWriteStream.write()` without backpressure handling, then reads the entire gzipped file into memory for upload. This directive fixes both the streaming performance and the remaining memory allocation bottleneck.

**Current architecture (as of 2026-03-13):**

1. `parseAndPersistStreamedCsv()` in `trigger/src/workflows/fmcsa-daily-diff.ts` (lines ~739–865):
   - Downloads CSV via `fetch` streaming response
   - Pipes through `csv-parse` stream parser
   - For each parsed row: `JSON.stringify()` → `ndjsonFileStream.write(line + "\n")`
   - After all rows: closes write stream, then runs `pipeline(createReadStream → createGzip → createWriteStream)` to gzip
   - Then: `readFile(gzippedTmpPath)` loads entire gzipped file into memory
   - Then: computes SHA-256 checksum on in-memory buffer
   - Then: uploads via TUS resumable upload (6MB chunks) from in-memory buffer
   - Then: sends manifest POST to FastAPI

2. `uploadPrebuiltArtifactAndIngest()` (lines ~642–737) receives the full `gzippedBytes: Uint8Array` and uploads it.

3. The TUS upload client (`createStorageClient`, lines ~488–541) receives the full `Uint8Array` and wraps it in a `Buffer`.

**Known problems in the current code:**

- **No backpressure on NDJSON writes.** `ndjsonFileStream.write(line + "\n")` is called in a hot loop without checking if the write stream's internal buffer is full. When the Node.js internal buffer fills up, writes are queued in memory. For a 2M-row feed where each JSON line is ~500 bytes, this can back up hundreds of MB in Node's internal write queue before the OS flushes to disk.

- **Entire gzipped artifact loaded into memory for upload.** `readFile(gzippedTmpPath)` loads the full gzipped file. For a 2M-row feed, the gzipped artifact is ~50–100MB. For the 13.3M-row Inspections Per Unit feed, it could be 500MB+. This defeats the purpose of the temp-file approach.

- **SHA-256 checksum computed on in-memory buffer.** The checksum could be computed incrementally during the gzip pipeline.

- **TUS upload receives full buffer.** The `tus-js-client` library accepts a `Buffer` or `Readable` — the current code always passes a `Buffer`. For large artifacts, it should stream from the file.

**Existing code to read:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — the entire file, especially:
  - `parseAndPersistStreamedCsv()` (lines ~739–865) — the streaming parse loop
  - `uploadPrebuiltArtifactAndIngest()` (lines ~642–737) — artifact upload and manifest POST
  - `createStorageClient()` (lines ~486–541) — TUS upload implementation
  - `buildNdjsonGzipped()` (line ~543) — non-streaming path (keep working as-is)
  - `shouldUseStreamingParser()` (line ~183) — determines which path a feed takes
  - `cleanupTmpFile()` (line ~867) — temp file cleanup helper
- `trigger/src/tasks/fmcsa-sms-motor-carrier-census-daily.ts` — example large streaming feed task (2.1M rows, `large-2x` machine)
- `trigger/src/tasks/fmcsa-sms-ab-pass-daily.ts` — example small streaming feed task (9K rows, no machine preset)
- `trigger/src/tasks/fmcsa-boc3-daily.ts` — example non-streaming feed task (works fine, do not change)
- `docs/fmcsa_feed_sizes.json` — feed size reference data
- `app/services/fmcsa_artifact_ingest.py` — FastAPI-side artifact ingest (already streams correctly, no changes needed)

---

### Deliverable 1: Backpressure-Aware NDJSON File Writes

In `parseAndPersistStreamedCsv()`, the `ndjsonFileStream.write(line + "\n")` call in the `for await` loop does not respect backpressure. When `write()` returns `false`, the caller must wait for the `'drain'` event before writing more.

Fix the streaming parse loop to handle backpressure:

- When `ndjsonFileStream.write()` returns `false`, pause and `await` the `'drain'` event before continuing the parse loop.
- This prevents Node from buffering unbounded NDJSON data in memory while the OS flushes to disk.
- The `for await` loop over the CSV parser naturally handles backpressure on the read side (pausing the download). The fix is on the write side only.
- Keep the existing progress logging at every 500K rows.
- Keep all existing error handling and temp file cleanup.

Commit standalone.

### Deliverable 2: Streaming Gzip with Incremental Checksum

Currently the flow is: gzip to temp file → `readFile()` entire gzipped file → compute checksum on buffer → pass buffer to upload.

Replace with a single streaming pipeline that computes the checksum incrementally:

- Use a `Transform` stream or `crypto.createHash('sha256')` as a passthrough in the gzip pipeline to compute the checksum during compression, not after.
- The gzip pipeline should still write to a temp file (the upload step needs a file path or buffer).
- After the pipeline completes, you have the checksum without needing to re-read the file.
- Remove the `readFile(gzippedTmpPath)` call.

Commit standalone.

### Deliverable 3: Stream-From-File TUS Upload

Currently `uploadPrebuiltArtifactAndIngest()` receives `gzippedBytes: Uint8Array` — the entire artifact in memory. The TUS client in `createStorageClient` wraps it in a `Buffer`.

Refactor so the TUS upload streams from the gzipped temp file instead of loading it into memory:

- Change `uploadPrebuiltArtifactAndIngest()` to accept a file path and file size instead of `gzippedBytes: Uint8Array`.
- Change `createStorageClient().upload()` to accept a file path and create a `createReadStream()` to pass to `tus-js-client`. The library accepts `Readable` streams — use that.
- The manifest POST still needs `rowCount` and `checksum`, which are already available from Deliverables 1 and 2 — no file read needed.
- Keep the non-streaming path (`uploadArtifactAndIngest` → `buildNdjsonGzipped`) working exactly as it does now for small feeds. Only the streaming path changes.
- Update `parseAndPersistStreamedCsv()` to pass the gzipped file path and size instead of reading the file into memory.

Commit standalone.

### Deliverable 4: Verify Small Feeds Still Work

The non-streaming path (`buildNdjsonGzipped` → `uploadArtifactAndIngest`) is used by 13 plain-text feeds. Verify it still compiles and its logic is untouched. The streaming path changes must not break the non-streaming path.

Also verify that the streaming path works for small feeds (e.g. SMS AB Pass at 9K rows) — the backpressure handling must not introduce deadlocks or performance regressions for small data.

Run `npx tsc --noEmit` to confirm no type errors.

Commit standalone (if any fixes needed).

---

**What is NOT in scope:**

- Do not change `app/services/fmcsa_artifact_ingest.py` or any FastAPI code. The server side already streams correctly.
- Do not change the non-streaming download/parse path (`downloadDailyDiffText` → `parseDailyDiffBody` → `uploadArtifactAndIngest`).
- Do not change cron schedules. They are currently disabled and will be re-enabled separately.
- Do not change feed configurations, field mappings, or `normalizeCsvRow`.
- Do not run deploy commands.
- Do not add new dependencies. `tus-js-client` is already installed; Node.js built-in `stream`, `crypto`, `fs`, `zlib` modules cover everything needed.
- Do not modify tests. If existing tests break due to the refactor, fix the type signatures to match but do not change test logic.

**Commit convention:** Each deliverable is one commit. Do not push.

**Performance target:** A 2M-row feed (SMS Motor Carrier Census, 43 columns) should complete the Trigger-side artifact creation (download → parse → NDJSON write → gzip → upload) in under 10 minutes on a `large-2x` machine, with peak memory usage staying under 500MB.

**When done:** Report back with:
(a) For each deliverable: what changed, file paths modified, and any judgment calls made.
(b) The peak memory concern: after all deliverables, what is the largest single allocation remaining in the streaming path? (It should be the TUS chunk size at 6MB, not the full artifact.)
(c) Any type errors from `npx tsc --noEmit`.
(d) Whether the non-streaming path compiles and is logically untouched.
(e) Anything to flag — risks, edge cases, or concerns about the approach.
