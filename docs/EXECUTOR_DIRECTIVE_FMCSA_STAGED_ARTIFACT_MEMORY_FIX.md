# Directive: FMCSA Staged Artifact Memory Fix

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA pipeline ingests CSV feeds from FMCSA.gov through Trigger.dev, then persists rows via FastAPI into Postgres. A staged artifact architecture was recently committed (not yet deployed) that replaces the old batch-by-batch HTTP loop with: Trigger downloads CSV → parses → writes gzipped NDJSON to Supabase Storage → sends a single manifest POST → FastAPI downloads the artifact, decompresses, parses NDJSON, and persists in chunks through the existing COPY+merge pipeline. This architecture must handle the heaviest feeds: `Company Census File` (4.4M rows, 147 columns) and `Vehicle Inspection File` (8.2M rows). The current implementation has two memory-safety bugs that will OOM both runtimes on these feeds. Both bugs must be fixed before this ships.

**Bug 1 — Trigger-side (`trigger/src/workflows/fmcsa-daily-diff.ts`):** The streaming parser path `parseAndPersistStreamedCsv()` (line ~685) accumulates every parsed row into `const allRows: FmcsaDailyDiffRow[] = []` (line ~712). For 8.2M rows with 147 columns, this means 8.2 million JS objects with full prototype chains, hidden classes, and per-property string headers — enough to OOM the Trigger.dev runtime. After the stream finishes, all rows are passed to `uploadArtifactAndIngest()` (line ~751) which calls `buildNdjsonGzipped(rows)` (line ~600) to serialize and gzip. The fix: serialize each row to an NDJSON string *during streaming* so you hold compact text, not structured objects.

**Bug 2 — FastAPI-side (`app/services/fmcsa_artifact_ingest.py`):** The `ingest_artifact()` function (line ~174) calls `gzip.decompress(gzipped_bytes)` — loading the *entire* decompressed artifact (potentially several GB for the largest feeds) into memory as a single `bytes` object. Then `parse_ndjson_rows(decompressed)` (line ~175) creates a full `list[FmcsaDailyDiffRow]` of all rows before chunking begins. The fix: use `gzip.GzipFile` for streaming decompression and parse + persist in chunks as you go.

**Existing code to read:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — focus on: `parseAndPersistStreamedCsv()` (~line 685), `buildNdjsonGzipped()` (~line 511), `uploadArtifactAndIngest()` (~line 589), `__testables` export (~line 1978). Also understand the non-streaming path via `parseDailyDiffBody` which uses `parseCsvSync` and passes rows to `uploadArtifactAndIngest()` (~line 804) — this path is fine as-is for small feeds.
- `app/services/fmcsa_artifact_ingest.py` — focus on: `ingest_artifact()` (~line 131), `parse_ndjson_rows()` (~line 117), `download_artifact_from_storage()` (~line 89), `verify_checksum()` (~line 111), `FMCSA_FEED_REGISTRY` (~line 49), `ChecksumMismatchError` (~line 254). Do not change the registry, download, or checksum logic.
- `tests/test_fmcsa_artifact_ingest.py` — the existing FastAPI-side test file. Has tests for `parse_ndjson_rows`, `verify_checksum`, feed registry coverage, `ingest_artifact` (small batch, chunked processing, checksum mismatch, unknown feed, chunk failure), and endpoint tests. You will update these tests in Deliverable 3.
- `app/services/fmcsa_daily_diff_common.py` — the persistence engine: `upsert_fmcsa_daily_diff_rows()`. **Do not modify this file.**

---

### Deliverable 1: Trigger-Side Streaming Artifact Write

Fix `parseAndPersistStreamedCsv()` in `trigger/src/workflows/fmcsa-daily-diff.ts` so it never holds all rows in memory as structured JS objects.

**The bug:** Lines ~712 and ~726 accumulate every row into `allRows: FmcsaDailyDiffRow[]`. Line ~751 passes `allRows` to `uploadArtifactAndIngest()`. For 4.4M+ rows, this OOMs.

**The fix — string accumulator approach:**

- Remove the `allRows: FmcsaDailyDiffRow[] = []` array entirely.
- Instead, as the CSV stream parser emits each row, immediately serialize it: `JSON.stringify(normalizeCsvRow(...)) + "\n"` and append that NDJSON line string to a string accumulator (e.g., an array of strings, or concatenate directly). Also maintain a `rowCount` integer counter.
- After the stream completes, join the accumulated NDJSON lines into a single string, gzip it with `gzipSync`, and compute the SHA-256 checksum of the gzipped bytes.
- Upload the gzipped bytes and send the manifest POST, just like the current `uploadArtifactAndIngest()` does.

This approach still holds all NDJSON text in memory, but a flat string is dramatically smaller than millions of JS objects. For Company Census (147 columns), each row as a JS object carries per-property overhead (hidden classes, property descriptors, individual string headers). The same row as an NDJSON string is a compact UTF-8 buffer with no per-field overhead — roughly 3-5x memory savings.

**What changes to `uploadArtifactAndIngest()`:**

The current signature is `uploadArtifactAndIngest(client, storage, payload, rows: FmcsaDailyDiffRow[], feedDate, observedAt)`. Two options:

1. Change `parseAndPersistStreamedCsv` to call `uploadArtifactAndIngest` with already-gzipped bytes + checksum + rowCount instead of raw rows. This means `uploadArtifactAndIngest` no longer calls `buildNdjsonGzipped` for the streaming path.
2. Or, inline the upload+manifest logic directly in `parseAndPersistStreamedCsv` after the stream completes.

Either approach is fine. The non-streaming path (line ~804) still passes `parsed.rows` to `uploadArtifactAndIngest()` and uses `buildNdjsonGzipped()` — that path must continue to work unchanged. `buildNdjsonGzipped()` must remain available and exported via `__testables`.

**Constraints:**

- The checksum and row count must still be accurate.
- The non-streaming path must not change.
- If even the NDJSON string approach is too large for 8.2M rows, you may write NDJSON lines to a temp file on disk and gzip from that file. But try the string accumulator approach first — it is simpler and likely sufficient. Document your reasoning in the report.

Commit standalone.

### Deliverable 2: FastAPI-Side Streaming Decompression and Chunked Parse

Fix `ingest_artifact()` in `app/services/fmcsa_artifact_ingest.py` so it does not buffer the entire decompressed artifact in memory.

**The bug:** Line ~174 calls `gzip.decompress(gzipped_bytes)` which materializes the entire decompressed artifact (potentially GB). Line ~175 calls `parse_ndjson_rows(decompressed)` which creates a complete `list[FmcsaDailyDiffRow]` before any chunking starts. Lines ~195-196 then chunk `rows` by index. Peak memory = gzipped bytes + full decompressed bytes + full rows list.

**The fix — streaming decompress-parse-persist:**

Replace the decompress → parse → chunk sequence (lines ~173-222) with:

1. Wrap `gzipped_bytes` in `io.BytesIO`, then open `gzip.GzipFile(fileobj=bio)`.
2. Iterate lines from the `GzipFile` (it supports `for line in gzip_file:`).
3. For each line: `json.loads(line)` to get a `FmcsaDailyDiffRow` dict. Append to a `chunk: list` and increment a `total_rows_parsed` counter.
4. When `len(chunk) == chunk_size`: call `upsert_func(source_context=source_context, rows=chunk)`, accumulate `rows_written`, increment `chunks_processed`, clear the chunk list.
5. After iteration: flush any remaining rows in a final partial chunk.

**What stays the same:**

- Everything before the decompress step: download, checksum verification, feed resolution, source context construction — all unchanged.
- The chunk failure behavior: stop on first failure, log with chunk number and rows processed, re-raise as `RuntimeError`.
- The `fmcsa_artifact_ingest_summary` log with all the same fields.
- The return envelope shape.

**What changes:**

- `artifact_decompress_parse_ms` timer: this field now measures the total time of the streaming decompress-parse-persist loop (since decompression and parsing are interleaved with persistence). Rename the internal timing variable or adjust the timer boundaries so it wraps the entire streaming+persist loop. Keep `total_persist_ms` as a separate timer if you want, or merge — just make sure the summary log still has both fields.
- `total_rows_received` in the summary and `rows_received` in the return dict: use `total_rows_parsed` (the running counter) instead of `len(rows)`.
- `parse_ndjson_rows()`: this function is no longer called by `ingest_artifact()`. You may leave the function in place (tests reference it) or remove it and update tests — your choice. If you leave it, that's fine; it just becomes unused by the main code path.

**Peak memory after fix:** One chunk of rows (e.g., 10K rows) + the gzipped bytes in memory. For Company Census: ~56 MB gzipped + ~10K rows chunk ≈ trivial. The old approach: ~56 MB gzipped + ~880 MB decompressed + ~4.4M row objects ≈ multi-GB.

Commit standalone.

### Deliverable 3: Update Tests

Update `tests/test_fmcsa_artifact_ingest.py` to match the new streaming behavior.

**FastAPI-side tests to update or add:**

- `TestIngestArtifact.test_chunked_processing`: This test creates 25 rows, passes `chunk_size=10`, and asserts 3 chunks of `[10, 10, 5]`. It should still pass with the streaming approach. Verify it does. If the internal implementation changed enough to break it, fix the test while preserving the assertion.
- `TestIngestArtifact.test_successful_ingest_small_batch`: Verify it still passes with streaming decompression.
- `TestIngestArtifact.test_chunk_failure_stops_processing`: Verify it still passes — the streaming approach must still stop on first failure.
- `TestParseNdjsonRows`: If `parse_ndjson_rows()` was removed, remove these tests. If it was kept, leave them.
- **New test — streaming decompression verification**: Add a test that creates a larger artifact (e.g., 100+ rows with `chunk_size=10`), mocks the download, and verifies that `upsert_func` is called the expected number of times (10 calls for 100 rows at chunk_size=10, or 11 calls for 105 rows). This proves the streaming path works end-to-end and handles the final partial chunk.

**Trigger-side tests:**

- There is no existing Trigger-side test file for the artifact functions. The `__testables` export includes `buildNdjsonGzipped` — this function is still used by the non-streaming path and should remain tested if a test file exists. If no test file exists, skip Trigger-side tests (there is no test infrastructure set up for Trigger in this repo beyond what `__testables` exports).

Commit standalone.

---

**What is NOT in scope:** No changes to `app/services/fmcsa_daily_diff_common.py`. No changes to `app/routers/internal.py` (the manifest endpoint handler). No changes to the `FMCSA_FEED_REGISTRY`. No changes to the non-streaming path (`parseDailyDiffBody` → `uploadArtifactAndIngest` for small feeds). No changes to `download_artifact_from_storage()` or `verify_checksum()`. No changes to the manifest POST shape or confirmation envelope shape. No deploy commands. No push.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) how the Trigger streaming path now works — string accumulator vs temp file, and how `uploadArtifactAndIngest` was adapted or bypassed for the streaming path, (b) how the FastAPI streaming decompression works — `GzipFile` iteration, chunk accumulation, timer adjustments, (c) peak memory profile comparison: old approach vs new approach for Company Census (4.4M rows, 147 cols) — even rough estimates are useful, (d) test updates — what changed, what was added, what each test proves, (e) anything to flag.
