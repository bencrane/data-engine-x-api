import assert from "node:assert/strict";
import test from "node:test";
import { gunzipSync } from "node:zlib";

import { createInternalApiClient } from "../internal-api.js";
import { createCapturingMockFetch } from "./test-helpers.js";

test("InternalApiClient.post() sends gzip-compressed body with Content-Encoding header", async () => {
  const payload = { rows: [{ id: 1, name: "test" }, { id: 2, name: "other" }] };
  const { fetchImpl, captured } = createCapturingMockFetch([
    { body: { data: { ok: true } } },
  ]);

  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl,
  });

  await client.post("/api/internal/test", payload);

  assert.equal(captured.length, 1);
  const req = captured[0];
  const headers = req.init?.headers as Record<string, string>;

  // Verify Content-Encoding header is set
  assert.equal(headers["Content-Encoding"], "gzip");
  // Verify Content-Type is still application/json
  assert.equal(headers["Content-Type"], "application/json");

  // Verify body is gzip-compressed and decompresses to original JSON
  const body = req.init?.body;
  assert.ok(body instanceof Buffer || body instanceof Uint8Array, "body should be a Buffer");
  const decompressed = gunzipSync(body as Buffer);
  assert.equal(decompressed.toString("utf-8"), JSON.stringify(payload));
});

test("compressed body decompresses to exact JSON.stringify output", async () => {
  const payload = {
    batch: Array.from({ length: 100 }, (_, i) => ({
      index: i,
      value: `item-${i}`,
      nested: { a: true, b: null },
    })),
  };

  const { fetchImpl, captured } = createCapturingMockFetch([
    { body: { data: { ok: true } } },
  ]);

  const client = createInternalApiClient({
    authContext: { orgId: "org-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl,
  });

  await client.post("/api/internal/fmcsa/test", payload);

  const body = captured[0].init?.body as Buffer;
  const decompressed = gunzipSync(body).toString("utf-8");
  assert.equal(decompressed, JSON.stringify(payload));
});
