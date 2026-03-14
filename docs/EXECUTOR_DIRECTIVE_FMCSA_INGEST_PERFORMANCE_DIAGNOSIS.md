**Directive: FMCSA Ingest Pipeline Performance Diagnosis — Identify Bottlenecks and Propose Targeted Fixes**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Important: This is a diagnosis directive, not an implementation directive.** You are not writing code. You are reading the current implementation critically, identifying where time is being spent, and producing a concrete analysis with specific recommendations. Your deliverable is a written report.

**Background:** The FMCSA staged artifact ingest pipeline downloads CSV feeds from data.transportation.gov, converts them to gzipped NDJSON artifacts, uploads to Supabase Storage, and sends a manifest POST so FastAPI can download and persist the data. The pipeline recently received fixes for backpressure-aware NDJSON writes and streaming gzip with incremental checksum (deployed version 20260313.7). However, the SMS Motor Carrier Census feed (2.1M rows, 43 columns) is still taking 36+ minutes end-to-end on a `large-2x` Trigger.dev machine. The target is under 10 minutes. The pipeline needs to handle 31 feeds daily, including several with 1M–13M rows, so understanding where time is actually spent is critical before making further changes.

**Current architecture (as of 2026-03-13):**

The end-to-end flow for a streaming feed has these distinct phases:

**Phase 1 — Trigger.dev: Download + Parse + Write NDJSON to disk**
- `parseAndPersistStreamedCsv()` in `trigger/src/workflows/fmcsa-daily-diff.ts` (lines ~740–881)
- Fetches CSV via `fetch(downloadUrl)` from Socrata (data.transportation.gov)
- Streams through `csv-parse` stream parser
- For each row: `JSON.stringify(normalizeCsvRow(...))` → `ndjsonFileStream.write(line + "\n")` with backpressure-aware drain handling
- For SMS Motor Carrier Census: 2.1M rows × 43 columns. Each NDJSON line contains `row_number`, `raw_values` (array of 43 strings), and `raw_fields` (object with 43 key-value pairs). This means each row is serialized with the data duplicated: once as an array, once as an object with full field names. At ~43 columns, each NDJSON line is approximately 800–1200 bytes.

**Phase 2 — Trigger.dev: Gzip + Checksum**
- `pipeline(createReadStream(ndjsonTmpPath) → createGzip() → hashPassthrough → createWriteStream(gzippedTmpPath))`
- Incremental SHA-256 computed via Transform passthrough during gzip

**Phase 3 — Trigger.dev: Read gzipped file into memory**
- `readFile(gzippedTmpPath)` — loads entire gzipped artifact into a `Buffer`
- For 2.1M rows, gzipped artifact is estimated 50–100MB

**Phase 4 — Trigger.dev: TUS upload to Supabase Storage**
- `tus-js-client` resumable upload in 6MB chunks
- Uses `Buffer` input (not streaming — a previous attempt to stream from file hung indefinitely)

**Phase 5 — Trigger.dev: Manifest POST to FastAPI**
- `writeDedicatedTableConfirmed()` sends manifest with feed metadata, artifact location, row count, checksum
- Timeout: `MANIFEST_INGEST_TIMEOUT_MS = 1_800_000` (30 minutes)
- The internal API client gzip-compresses the JSON body before sending

**Phase 6 — FastAPI: Download artifact from Supabase Storage**
- `download_artifact_from_storage()` in `app/services/fmcsa_artifact_ingest.py` (line 90–109)
- `httpx.get()` with 600s timeout — downloads the entire gzipped artifact into memory (`response.content`)

**Phase 7 — FastAPI: Verify checksum + Decompress + Parse + Upsert**
- SHA-256 checksum verification on in-memory gzipped bytes
- Streams through `gzip.GzipFile` line-by-line, accumulates a `chunk` list of 10,000 rows
- Each chunk calls `upsert_func(source_context=..., rows=chunk)`
- For 2.1M rows at chunk_size=10,000: **210 chunk upserts**
- Each upsert in `upsert_fmcsa_daily_diff_rows()` (`app/services/fmcsa_daily_diff_common.py`):
  1. Calls `row_builder()` on each row (43-column field mapping with parse_int, parse_bool, clean_text, parse_fmcsa_date, etc.)
  2. Adds metadata columns (feed_date, row_position, source_provider, source_feed_name, source_download_url, source_file_variant, source_observed_at, source_task_id, source_schedule_id, source_run_metadata as JSONB, raw_source_row as JSONB, updated_at)
  3. Filters columns to match live table schema
  4. Creates temp table, COPY rows in, INSERT...ON CONFLICT DO UPDATE (merge), COMMIT
  5. Each chunk: temp table create + COPY + merge SQL + commit — 210 times for 2.1M rows

**Phase 8 — Trigger.dev: Artifact cleanup**
- Deletes artifact from Supabase Storage after confirmed success
- TTL cleanup of artifacts older than 7 days

**Key data points:**

| Feed | Rows | Columns | Est. NDJSON size | Est. gzipped | Chunk upserts |
|---|---|---|---|---|---|
| SMS Motor Carrier Census | 2,079,041 | 43 | ~1.5–2.5 GB | ~50–100 MB | 208 |
| SMS Input - Inspection | 5,778,075 | 37 | ~3–5 GB | ~150–300 MB | 578 |
| SMS Input - Violation | 6,593,446 | 13 | ~2–3 GB | ~100–200 MB | 660 |
| Vehicle Inspection File | 8,182,384 | 48 | ~6–10 GB | ~300–500 MB | 819 |
| Vehicle Inspections & Violations | 12,945,593 | 17 | ~5–8 GB | ~200–400 MB | 1295 |
| Inspections Per Unit | 13,259,174 | 29 | ~8–12 GB | ~400–600 MB | 1326 |
| Company Census File | 4,402,459 | 109 | ~8–15 GB | ~400–800 MB | 441 |
| Crash File | 4,906,670 | 81 | ~8–12 GB | ~300–600 MB | 491 |

**Existing code to read — read ALL of these carefully:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — the entire file, especially:
  - `parseAndPersistStreamedCsv()` (lines ~740–881) — streaming parse loop with backpressure and temp file writes
  - `uploadPrebuiltArtifactAndIngest()` (lines ~642–737) — TUS upload, manifest POST, artifact cleanup
  - `createStorageClient()` (lines ~484–541) — TUS upload implementation
  - `normalizeCsvRow()` (line ~400) — per-row normalization (produces `raw_values` + `raw_fields` duplication)
  - `FMCSA_LONG_RUNNING_STREAM_TIMEOUTS` (line ~172) — download 3.3M ms, persistence 300K ms
  - `MANIFEST_INGEST_TIMEOUT_MS` (line ~162) — 30 minutes
  - `FmcsaDailyDiffRow` type (line ~71) — the shape of each serialized row
  - Feed configs for large feeds: `FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED`, `FMCSA_SMS_INPUT_INSPECTION_FEED`, `FMCSA_SMS_INPUT_VIOLATION_FEED`, `FMCSA_CRASH_FILE_FEED`, `FMCSA_COMPANY_CENSUS_FILE_FEED`, `FMCSA_VEHICLE_INSPECTION_FILE_FEED`, `FMCSA_INSPECTIONS_PER_UNIT_FEED`
- `trigger/src/workflows/internal-api.ts` — internal API client (gzip-compresses request body, timeout handling)
- `trigger/src/workflows/persistence.ts` — `writeDedicatedTableConfirmed` / `confirmedInternalWrite`
- `app/services/fmcsa_artifact_ingest.py` — FastAPI-side artifact download, decompress, parse, chunked upsert
- `app/services/fmcsa_daily_diff_common.py` — `upsert_fmcsa_daily_diff_rows()`: row builder, temp table COPY, merge SQL, connection pool
- `app/services/motor_carrier_census_records.py` — SMS Motor Carrier Census row builder (43-column field mapping)
- `docs/fmcsa_feed_sizes.json` — feed size reference data
- `trigger/src/tasks/fmcsa-sms-motor-carrier-census-daily.ts` — task config (machine: `large-2x`, maxDuration: 43200)

---

### Deliverable 1: Phase-by-Phase Time Budget Analysis

For the SMS Motor Carrier Census feed (2.1M rows, 43 columns), estimate where time is being spent across the 8 phases described above. For each phase, provide:

- **Estimated wall-clock time** based on the data volumes, computational work, and I/O characteristics
- **What dominates**: CPU, disk I/O, network I/O, or database
- **Evidence**: cite specific code paths, data sizes, and known bottleneck patterns

Key questions to answer:

1. **Socrata download speed**: The CSV is downloaded from `data.transportation.gov` via streaming fetch. Socrata is known for variable download speeds (sometimes 1–5 MB/s). For a 2.1M-row × 43-column CSV, how large is the raw CSV and how long would the download take at realistic Socrata speeds?

2. **NDJSON serialization overhead**: Each row is serialized as `{ row_number, raw_values: string[43], raw_fields: { field1: "val1", ... field43: "val43" } }`. The `raw_values` and `raw_fields` contain the same data in two different shapes. What is the per-row serialization cost, and for 2.1M rows, how much total NDJSON data is written to disk?

3. **Gzip pipeline throughput**: Node.js `createGzip()` streaming through 1.5–2.5 GB of NDJSON — what throughput is realistic on a Trigger.dev `large-2x` machine?

4. **TUS upload throughput**: Uploading 50–100MB in 6MB chunks to Supabase Storage — what is realistic latency per chunk and total upload time?

5. **FastAPI-side artifact download**: `httpx.get()` downloading 50–100MB from Supabase Storage internal network — how long?

6. **FastAPI-side upsert throughput**: 210 chunk upserts, each doing: row_builder on 10K rows (43 field mappings with type parsing), build COPY payload, create temp table, COPY, merge SQL, commit. How long per chunk? How long total?

7. **What is the single largest time sink?** Is it Socrata download, NDJSON serialization + disk writes, gzip, TUS upload, or server-side upserts? Quantify your best estimate for each.

### Deliverable 2: Data Shape Efficiency Analysis

Critically evaluate the `FmcsaDailyDiffRow` data shape and the NDJSON artifact format:

```typescript
{
  row_number: number;
  raw_values: string[];     // ["val1", "val2", ..., "val43"]
  raw_fields: Record<string, string>;  // { "DOT_NUMBER": "val1", "LEGAL_NAME": "val2", ... }
}
```

Questions to address:

1. **Duplication**: `raw_values` and `raw_fields` contain the same data. For a 43-column feed, this doubles the per-row payload. Is this duplication necessary? Does the server side (`fmcsa_artifact_ingest.py` → `upsert_fmcsa_daily_diff_rows` → `row_builder`) use `raw_values` at all, or only `raw_fields`? Check each row builder to determine which fields they actually access.

2. **NDJSON line size**: With field names repeated per row (e.g., `"PRIVATE_PASSENGER_NONBUSINESS"` appears 2.1M times), what percentage of the artifact is field-name overhead? Would a columnar or header-once format significantly reduce artifact size?

3. **raw_source_row in the database**: The upsert layer adds `raw_source_row` as a JSONB column containing the full `FmcsaDailyDiffRow` (row_number + raw_values + raw_fields). For 2.1M rows × 43 columns, what is the estimated database storage cost of this redundancy? Is it needed for audit/debugging, or is it dead weight?

4. **If `raw_values` were dropped**: estimate the reduction in NDJSON file size, gzipped artifact size, TUS upload time, and server-side processing time.

### Deliverable 3: Server-Side Upsert Performance Analysis

Deeply analyze the FastAPI-side upsert path for a 2.1M-row feed:

1. **Connection pool sizing**: `_get_fmcsa_connection_pool()` creates a pool with `min_size=1, max_size=4`. All 210 chunks are processed sequentially in a single request handler. Is the pool sized appropriately? Could chunk upserts be parallelized within the pool?

2. **Per-chunk overhead**: Each of 210 chunks does: acquire connection → create temp table → COPY 10K rows → merge SQL → commit → release connection. How much of each chunk's time is overhead (temp table DDL, connection acquire, commit) vs. actual data work (COPY + merge)?

3. **Chunk size tuning**: The current `DEFAULT_CHUNK_SIZE = 10_000`. For a 43-column table with ~100 columns in the actual database row (after metadata expansion), would larger chunks (25K, 50K) reduce per-chunk overhead without causing memory issues? What is the optimal chunk size?

4. **COPY payload construction**: `_build_copy_payload()` constructs a tab-delimited text payload in memory for each chunk. For 10K rows × ~100 columns, this is a significant string allocation. Is this a bottleneck?

5. **The merge SQL pattern**: The INSERT...ON CONFLICT DO UPDATE touches every mutable column. For a table with ~100 columns and 2.1M rows, what indexes exist and what is the expected merge performance? Could the upsert strategy be improved (e.g., truncate-and-reload for full-snapshot feeds)?

6. **Request timeout**: The manifest POST has `MANIFEST_INGEST_TIMEOUT_MS = 1_800_000` (30 minutes). The entire download + decompress + parse + 210 chunk upserts runs within this single HTTP request. Is this the right architecture, or should the server-side work be async (e.g., return immediately, process in background, callback when done)?

### Deliverable 4: Architecture-Level Recommendations

Based on your analysis in Deliverables 1–3, provide a prioritized list of specific, implementable recommendations. For each recommendation:

- **Expected time savings** (estimated minutes saved for the 2.1M-row feed)
- **Implementation complexity** (trivial / small / medium / large)
- **Risk** (what could go wrong)
- **Dependencies** (does it require FastAPI changes, Trigger changes, or both?)

Specifically evaluate these potential optimizations (but do not limit yourself to these — propose others if the analysis reveals better opportunities):

1. **Drop `raw_values` from the NDJSON artifact** — if server-side row builders only use `raw_fields`, eliminate the array duplication. Reduces artifact size ~40%.

2. **Increase upsert chunk size** — larger chunks mean fewer round-trips (temp table create + COPY + merge + commit).

3. **Truncate-and-reload for full-snapshot feeds** — SMS Motor Carrier Census is a complete snapshot, not a differential. Instead of 210 individual ON CONFLICT upserts, could the server truncate the feed_date partition and bulk-load?

4. **Parallelize chunk upserts** — the connection pool has `max_size=4` but only one connection is used sequentially. Could 2–4 chunks be upserted concurrently?

5. **Skip Supabase Storage entirely for feeds under a size threshold** — instead of upload → manifest → download → process, could the Trigger side POST the NDJSON directly to FastAPI in chunks, bypassing the artifact storage round-trip?

6. **Async server-side processing** — instead of blocking the HTTP request for 30 minutes, return a job ID and process in background. The Trigger side polls for completion.

7. **Any other opportunities** you identify from reading the code.

---

**What is NOT in scope:**

- Do not write code, SQL, Python, or TypeScript.
- Do not change any files.
- Do not run tests, builds, or deploy commands.
- Do not change feed configurations, field mappings, or cron schedules.
- Do not propose changes to the non-streaming path (small plain-text feeds work fine).
- Do not propose new dependencies unless clearly justified.

**Deliverable format:** A single written report covering Deliverables 1–4, structured with clear headings and quantified estimates. Use tables where appropriate.

**When done:** Report back with:
(a) The estimated time budget breakdown for SMS Motor Carrier Census (2.1M rows) across all 8 phases.
(b) The single largest bottleneck and estimated percentage of total time.
(c) Your top 3 recommendations ranked by (time saved / implementation effort).
(d) Whether the current 36-minute runtime is explainable from the analysis, or whether there is an unexplained gap suggesting a bug or infrastructure issue.
(e) Anything to flag — risks, architectural concerns, or surprises in the code.
