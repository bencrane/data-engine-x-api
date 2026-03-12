# Directive: FMCSA Internal Request Gzip Compression

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** FMCSA bulk ingestion sends large JSON request bodies from Trigger.dev to FastAPI internal endpoints. A measured local benchmark on the widest current feed (`Company Census File`, 147 columns) shows that a single 10,000-row batch serializes to `35.22 MB` of JSON. Gzip compresses that to `2.27 MB` (6.4% of raw) with only `0.231s` compress CPU and `0.044s` decompress CPU. With `441` batches per Company Census run, the cumulative on-wire savings are substantial. This is the highest-ROI quick win identified in the performance diagnosis (`docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`). The change must be backward-compatible: if the Trigger side sends an uncompressed request (no `Content-Encoding` header), the FastAPI side must still accept it as-is.

**What this directive does NOT address:** This directive does not touch the database persistence logic inside `app/services/fmcsa_daily_diff_common.py`. A separate directive handles instrumentation and connection pooling in that file. Do not modify that file.

**Existing code to read:**

- `CLAUDE.md`
- `docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md` — measured compression ratios and CPU costs
- `trigger/src/workflows/internal-api.ts` — the `InternalApiClient.post()` method that serializes and sends all internal requests
- `trigger/src/workflows/fmcsa-daily-diff.ts` — the FMCSA daily diff workflow that calls `writeDedicatedTableConfirmed()` for batch persistence
- `trigger/src/workflows/persistence.ts` — the `writeDedicatedTableConfirmed()` and `confirmedInternalWrite()` wrappers
- `app/routers/internal.py` — all 18 FMCSA `upsert-batch` endpoints that receive the request bodies

---

### Deliverable 1: Trigger-Side Gzip Compression

Add gzip compression to the `InternalApiClient.post()` method in `trigger/src/workflows/internal-api.ts` for FMCSA batch requests.

Requirements:

- After `JSON.stringify(payload)`, gzip the resulting buffer before passing it as the `fetch` body.
- Set `Content-Encoding: gzip` on the outgoing request.
- Keep `Content-Type: application/json` — the content type is still JSON, the encoding is the transport layer.
- Use Node.js built-in `zlib.gzipSync()` or the async `zlib.gzip()` via `util.promisify`. Do not add new npm dependencies for this.
- The compression must apply to all posts made through `InternalApiClient.post()`, not just FMCSA paths. Every internal POST benefits from smaller bodies, and the FastAPI decompression (Deliverable 2) will handle all paths uniformly. If for any reason you judge that blanket compression is risky, you may gate it behind an opt-in flag on `InternalPostOptions` — but the default should be compressed, and the FMCSA workflow must use it.
- Do not change the `InternalApiClient` constructor signature, the `InternalPostOptions` interface (beyond an optional compression flag if needed), or the response-handling logic.
- Do not change the FMCSA workflow payload shape, the `writeDedicatedTableConfirmed` interface, or the `confirmedInternalWrite` wrapper.

Commit standalone.

### Deliverable 2: FastAPI-Side Gzip Decompression

Add transparent gzip decompression on the FastAPI side so that any request arriving with `Content-Encoding: gzip` is decompressed before FastAPI/Starlette parses the JSON body.

Requirements:

- Implement this as ASGI middleware or a FastAPI middleware that intercepts the raw request body. The middleware must:
  - Check for `Content-Encoding: gzip` (case-insensitive).
  - If present, read the raw body, decompress with `gzip.decompress()` or `zlib.decompress(body, zlib.MAX_WBITS | 16)`, and replace the request body stream with the decompressed bytes.
  - Remove or clear the `Content-Encoding` header after decompression so downstream Starlette/FastAPI body parsing sees plain JSON.
  - If `Content-Encoding` is absent or not `gzip`, pass the request through unchanged. This preserves backward compatibility with any caller that does not compress.
- Place the middleware in a new file `app/middleware/gzip_request.py`. Register it in `app/main.py`.
- The middleware must apply to all routes, not just FMCSA paths. It is a generic transport optimization.
- Do not add new pip dependencies. Python's `gzip` or `zlib` stdlib modules are sufficient.
- Do not change the Pydantic request models, the endpoint handler signatures, or the response envelope shape.
- Add a safety limit: if the decompressed body exceeds `500 MB`, reject the request with HTTP `413 Request Entity Too Large`. This prevents decompression-bomb abuse. The limit should be a constant at the top of the middleware file, easy to adjust.

Commit standalone.

### Deliverable 3: Tests

Add tests that validate the compression round-trip works correctly.

Trigger-side tests (in `trigger/` test infrastructure):

- Verify that `InternalApiClient.post()` sends a gzip-compressed body with `Content-Encoding: gzip` header.
- Verify that the compressed body, when decompressed, equals the original `JSON.stringify(payload)`.
- Use a mock `fetch` implementation that captures the outgoing request for assertion. The existing `InternalApiClient` constructor accepts a `fetchImpl` parameter — use that.

FastAPI-side tests (in `tests/`):

- Verify that a gzipped JSON request body with `Content-Encoding: gzip` is correctly decompressed and parsed by the middleware, producing the expected Pydantic model.
- Verify that a normal uncompressed JSON request body (no `Content-Encoding` header) still works unchanged.
- Verify that a request exceeding the `500 MB` decompressed size limit returns HTTP `413`.
- Use FastAPI's `TestClient` for these tests. You may target any existing FMCSA upsert-batch endpoint or create a minimal test endpoint — your judgment.

Commit standalone.

---

**What is NOT in scope:** No changes to `app/services/fmcsa_daily_diff_common.py`. No changes to the FMCSA database persistence logic, connection handling, or instrumentation. No changes to the Pydantic request/response models. No changes to the FMCSA workflow payload shape or batch size logic. No new npm or pip dependencies. No deploy commands. No push.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) how Trigger-side compression is implemented (sync vs async, compression level, where in the call chain), (b) how FastAPI-side decompression middleware works (ASGI vs Starlette middleware, where registered, header handling), (c) the decompressed size safety limit and how it is enforced, (d) backward-compatibility behavior when `Content-Encoding` is absent, (e) test count and what each test proves, (f) anything to flag — especially if you discovered that the current Trigger.dev runtime or Railway proxy already handles `Content-Encoding` in a way that conflicts with this approach.
