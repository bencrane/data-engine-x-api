**Directive: Fix `fmcsa-boc3-all-history` and `fmcsa-inshist-all-history` 12-Hour Timeout**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Two FMCSA all-history plain-text feeds (`fmcsa-boc3-all-history` and `fmcsa-inshist-all-history`) have timed out at 12 hours (MAX_DURATION_EXCEEDED) three days running (March 14, 15, 16). The error observed is `TypeError: terminated` with cause `SocketError: other side closed` — the FMCSA server drops the HTTP connection mid-download. After the connection drops, the task hangs silently until it hits the 12-hour `maxDuration` ceiling. Other all-history feeds (rejected, actpendinsur, authhist) complete successfully on the same code and config.

**Root cause (confirmed by code review):** In `parseAndPersistStreamedCsv()`, the download stream is wired to the CSV parser via:

```typescript
const inputStream = Readable.fromWeb(response.body as any);
inputStream.pipe(parser);
```

Node.js `.pipe()` does **not** propagate errors from the source stream to the destination. When the FMCSA server closes the socket mid-download, `inputStream` emits an `'error'` event, but `parser` never receives it. The `for await (const record of parser)` loop hangs indefinitely waiting for records that will never arrive. The `AbortSignal.timeout(3_300_000)` on the original `fetch()` call does not help because it fires on the fetch response object, not on the parser stream.

**Existing code to read:**

- `trigger/src/workflows/fmcsa-daily-diff.ts` — the entire file, especially:
  - `parseAndPersistStreamedCsv()` (lines ~739-893): the function with the broken error propagation
  - `downloadDailyDiffResponse()` (lines ~436-455): the download function with AbortSignal
  - `FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING` (line ~176): config spread for these feeds
  - `FMCSA_LONG_RUNNING_STREAM_TIMEOUTS` (line ~170): `downloadTimeoutMs: 3_300_000` (55 min), `persistenceTimeoutMs: 300_000`
  - `formatStreamingWorkflowError()` (lines ~200-228): error formatter
  - `FMCSA_BOC3_ALL_HISTORY_FEED` (line ~1172): `downloadUrl: "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain"`, `expectedFieldCount: 9`, has `FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING`
  - `FMCSA_INSHIST_ALL_HISTORY_FEED` (line ~1161): `downloadUrl: "https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain"`, `expectedFieldCount: 17`, has `FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING`
  - `FMCSA_AUTHHIST_ALL_HISTORY_FEED` (line ~1204): same config pattern, completes in ~25-30 min — use as reference for what "working" looks like
  - `runFmcsaDailyDiffWorkflow()` (line ~891): the streaming branch calls `downloadDailyDiffResponse()` then `parseAndPersistStreamedCsv()`
- `trigger/src/tasks/fmcsa-boc3-all-history.ts` — task definition, `machine: "large-2x"`, `maxDuration: 43200` (12h)
- `trigger/src/tasks/fmcsa-inshist-all-history.ts` — same pattern

---

### Deliverable 1: Fix Stream Error Propagation in `parseAndPersistStreamedCsv()`

The core bug is that `.pipe()` does not forward errors. When `inputStream` emits an `'error'` event, `parser` must be destroyed so that `for await (const record of parser)` throws instead of hanging.

**Fix:** After `inputStream.pipe(parser)`, add an error handler on `inputStream` that destroys the parser with the same error:

```typescript
const inputStream = Readable.fromWeb(response.body as any);
inputStream.pipe(parser);
inputStream.on("error", (err) => {
  parser.destroy(err);
});
```

This ensures any download stream error (socket close, timeout abort, network failure) propagates to the parser, which causes `for await` to throw, which hits the `catch (error) { throw formatStreamingWorkflowError(...) }` handler and surfaces the error instead of hanging.

Also add the reverse direction — if the parser errors independently (malformed CSV, row validation), destroy the input stream to stop the download:

```typescript
parser.on("error", (err) => {
  inputStream.destroy(err);
});
```

**Important:** The `for await (const record of parser)` loop already has a try/catch wrapper that calls `formatStreamingWorkflowError`. Verify that after your change, a stream error results in a clean task failure with an error message — not a hang. The error should look like: `"BOC3 - All With History CSV parsing failed: terminated"` or similar.

**This fix applies to ALL feeds that use `parseAndPersistStreamedCsv`**, not just the two broken ones. That is correct and intended — error propagation should work for every streaming feed.

Commit standalone.

---

### Deliverable 2: Add Download Retry with Exponential Backoff

The FMCSA server dropping the connection is likely transient — these are large files served from a government CDN. A retry on the full download+parse cycle should succeed on subsequent attempts.

**Wrap the streaming branch in `runFmcsaDailyDiffWorkflow()` with retry logic.** When the streaming path fails with a download/socket error, retry the entire flow (download + parse + persist) from scratch. Do NOT retry individual chunks — the snapshot-replace semantics (`is_first_chunk: true` on chunk 0) mean a partial ingest followed by a retry starting at chunk 0 will correctly DELETE and re-insert.

**Retry parameters:**
- Maximum 3 attempts total (1 initial + 2 retries)
- Backoff: 30 seconds after first failure, 120 seconds after second failure
- Only retry on download/socket errors (errors where the stream was terminated by the remote side). Do NOT retry on:
  - Persistence errors (`InternalApiError`, `PersistenceConfirmationError`)
  - Validation errors (header mismatch, row width mismatch)
  - Timeout errors from the persistence layer (`InternalApiTimeoutError`)

**Where to implement:** In `runFmcsaDailyDiffWorkflow()`, wrap the streaming branch (the `if (shouldUseStreamingParser(payload.feed))` block). The non-streaming artifact branch does NOT need retry logic — it downloads the full text in one shot and the feeds using it are small enough to succeed reliably.

**How to detect retryable errors:** The socket error surfaces as a generic `Error` with message containing `"terminated"` or `"socket"` or `"ECONNRESET"` or `"other side closed"`. After your Deliverable 1 fix, this will be wrapped by `formatStreamingWorkflowError` as `"${feedName} CSV parsing failed: terminated"` or similar. Check if the error message includes keywords indicating a download/connection failure. A simple heuristic:

```typescript
function isRetryableDownloadError(error: unknown): boolean {
  if (error instanceof InternalApiError || error instanceof InternalApiTimeoutError || error instanceof PersistenceConfirmationError) {
    return false;
  }
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    return msg.includes("terminated") || msg.includes("socket") || msg.includes("econnreset") || msg.includes("other side closed") || msg.includes("download failed");
  }
  return false;
}
```

**Logging:** Log each retry attempt with `logger.warn("fmcsa streaming retry", { feed_name, attempt, max_attempts, error_message, backoff_ms })`.

**Important:** Each retry attempt calls `downloadDailyDiffResponse()` again, getting a fresh HTTP response and a fresh stream. The previous response/stream is dead and does not need cleanup.

Commit standalone.

---

### Deliverable 3: Investigate File Sizes and Assess Download Viability

Before declaring the fix complete, the executor must understand what these feeds look like in practice.

**Task:** Download both files manually using `curl` with timing. Run these from the Trigger.dev machine or locally — the goal is to understand file size and download time:

```bash
curl -o /dev/null -w "size: %{size_download}, time: %{time_total}s, speed: %{speed_download} bytes/sec\n" \
  "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain"

curl -o /dev/null -w "size: %{size_download}, time: %{time_total}s, speed: %{speed_download} bytes/sec\n" \
  "https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain"
```

Also download a sample of each to count rows:

```bash
curl -s "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain" | wc -l
curl -s "https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain" | wc -l
```

**Report findings in the final report.** Include: file size in MB, download time, estimated row count, whether the download completes or gets dropped.

**If the plain-text download consistently fails** (drops connection before completing), note this in the report. The feeds may need to switch to the Socrata CSV export endpoint (`https://data.transportation.gov/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD`) in a follow-up directive. But do NOT switch the download URL in this directive — the retry logic from Deliverable 2 should be validated first.

**If the files are very large** (>500MB or >5M rows), note this in the report with an estimate of how many streaming chunks they will produce.

This deliverable produces investigation data, not code. No commit needed.

---

### Deliverable 4: Verify Error Propagation Works

Write a minimal test or manual verification that confirms the error propagation fix works:

1. Check that `parseAndPersistStreamedCsv` properly throws when the input stream errors mid-parse, rather than hanging.
2. If there are existing tests in `trigger/src/tasks/__tests__/`, add a test case that simulates a stream error (create a Readable that emits an error after a few records, pipe it through the parser, and verify the `for await` loop throws).
3. If no test infrastructure exists for this, describe in the report how you manually verified the fix (e.g., "injected a stream.destroy(new Error('test')) after 100 records and confirmed the task throws within 1 second").

Run `cd trigger && npx tsc --noEmit` to verify no type errors.

Commit standalone (if test code was added).

---

**What is NOT in scope:**

- Do not change the download URLs for these feeds. If the plain-text URL is unreliable, note it in the report — the URL change will be a separate directive.
- Do not change `downloadTimeoutMs` or `persistenceTimeoutMs` values. The current 55-minute download timeout is appropriate for large streaming downloads.
- Do not change the non-streaming artifact path. Only `parseAndPersistStreamedCsv` and `runFmcsaDailyDiffWorkflow` (streaming branch only) are in scope.
- Do not change feed configs, cron schedules, `writeBatchSize`, or machine sizes.
- Do not change `flushChunk`, the direct chunk POST logic, or any persistence code.
- Do not modify Python code.
- Do not add new dependencies.
- Do not run deploy commands.

**Commit convention:** Deliverables 1 and 2 are separate commits. Deliverable 3 is investigation only (no commit). Deliverable 4 is a commit if test code was added. Do not push.

**When done:** Report back with:
(a) The error propagation fix — exact lines changed, and confirmation that a destroyed input stream causes `for await` to throw immediately rather than hang.
(b) The retry logic — where it lives, what errors trigger a retry, what the backoff schedule is.
(c) File size investigation results — size in MB, row count estimate, download time, whether the download completes reliably.
(d) `npx tsc --noEmit` output.
(e) Whether any existing tests were affected and what test coverage was added.
(f) Assessment: will the retry logic be sufficient, or do these feeds likely need a URL change to the CSV export endpoint?
(g) Anything to flag — risks, edge cases, or follow-up work needed.
