import assert from "node:assert/strict";
import test from "node:test";

import { InternalApiClient, InternalApiError, InternalApiTimeoutError } from "../../workflows/internal-api.js";
import { PersistenceConfirmationError } from "../../workflows/persistence.js";
import {
  FMCSA_BOC3_ALL_HISTORY_FEED,
  runFmcsaDailyDiffWorkflow,
  __testables,
} from "../../workflows/fmcsa-daily-diff.js";

const { isRetryableDownloadError } = __testables;

// ---------------------------------------------------------------------------
// isRetryableDownloadError
// ---------------------------------------------------------------------------

test("isRetryableDownloadError returns true for socket/terminated errors", () => {
  assert.equal(isRetryableDownloadError(new Error("TypeError: terminated")), true);
  assert.equal(isRetryableDownloadError(new Error("SocketError: other side closed")), true);
  assert.equal(isRetryableDownloadError(new Error("read ECONNRESET")), true);
  assert.equal(isRetryableDownloadError(new Error("BOC3 download failed: terminated")), true);
});

test("isRetryableDownloadError returns false for persistence/validation errors", () => {
  assert.equal(
    isRetryableDownloadError(
      new InternalApiError({ message: "500", path: "/api/internal/test", statusCode: 500 }),
    ),
    false,
  );
  assert.equal(
    isRetryableDownloadError(
      new InternalApiTimeoutError({ path: "/api/internal/test", timeoutMs: 5000 }),
    ),
    false,
  );
  assert.equal(
    isRetryableDownloadError(
      new PersistenceConfirmationError({ path: "/api/internal/test", message: "fail" }),
    ),
    false,
  );
});

test("isRetryableDownloadError returns false for unrelated errors", () => {
  assert.equal(isRetryableDownloadError(new Error("header mismatch")), false);
  assert.equal(isRetryableDownloadError(new Error("row width mismatch")), false);
  assert.equal(isRetryableDownloadError("string error"), false);
  assert.equal(isRetryableDownloadError(null), false);
});

// ---------------------------------------------------------------------------
// Stream error propagation through runFmcsaDailyDiffWorkflow
// ---------------------------------------------------------------------------

test("streaming workflow throws within 2s when download stream errors mid-parse", async () => {
  // Mock fetch: returns a ReadableStream that emits a few CSV rows then errors.
  // BOC3 all-history has 9 fields, no header row.
  const mockFetch = async (): Promise<Response> => {
    const readable = new ReadableStream({
      start(controller) {
        const rows = [
          "12345,100000,John Doe,ACME Inc,Attn,123 Main St,Anytown,NY,12345\n",
          "12346,100001,Jane Doe,Widget Co,Attn,456 Oak Ave,Somewhere,CA,90210\n",
        ];
        for (const row of rows) {
          controller.enqueue(new TextEncoder().encode(row));
        }
        // Simulate a stream error after 50ms. Use a non-retryable message
        // so the test doesn't wait through the 30s+120s retry backoff.
        setTimeout(() => {
          controller.error(new Error("simulated stream failure"));
        }, 50);
      },
    });

    return new Response(readable, {
      status: 200,
      headers: { "content-type": "text/plain" },
    });
  };

  // Mock internal API client and storage — provide to avoid env var errors.
  const mockClient = new InternalApiClient({
    authContext: { orgId: "test" },
    apiUrl: "http://localhost:9999",
    internalApiKey: "test-key",
  });
  const mockStorage = {
    upload: async () => ({ error: null }),
    remove: async () => ({ error: null }),
    createBucket: async () => ({ error: null }),
    list: async () => ({ data: [], error: null }),
  };

  const start = Date.now();
  await assert.rejects(
    () =>
      runFmcsaDailyDiffWorkflow(
        {
          feed: FMCSA_BOC3_ALL_HISTORY_FEED,
          schedule: { timestamp: new Date().toISOString() },
        },
        { fetchImpl: mockFetch as typeof fetch, client: mockClient, supabaseClient: mockStorage as any },
      ),
    (error: Error) => {
      assert.ok(
        error.message.includes("BOC3") || error.message.includes("simulated stream failure"),
        `Expected error to mention BOC3 or simulated stream failure, got: ${error.message}`,
      );
      return true;
    },
  );
  const elapsed = Date.now() - start;

  // Key assertion: error propagation causes fast failure, not a 12-hour hang.
  assert.ok(elapsed < 2000, `Expected fast failure but took ${elapsed}ms`);
});
