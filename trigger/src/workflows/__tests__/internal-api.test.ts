import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient, InternalApiError, InternalApiTimeoutError } from "../internal-api.js";
import { executeOperation } from "../operations.js";
import { createMockFetch, timeoutError } from "./test-helpers.js";

test("internal API client returns enveloped data on success", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        body: {
          data: {
            ok: true,
          },
        },
      },
    ]),
  });

  const response = await client.post<{ ok: boolean }>("/api/internal/test", { hello: "world" });

  assert.deepEqual(response, { ok: true });
});

test("executeOperation returns structured operation result", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        body: {
          data: {
            run_id: "run-123",
            operation_id: "company.enrich.profile",
            status: "found",
            output: {
              company_name: "Acme",
            },
            provider_attempts: [],
          },
        },
      },
    ]),
  });

  const result = await executeOperation(client, {
    operationId: "company.enrich.profile",
    entityType: "company",
    input: { company_domain: "acme.com" },
  });

  assert.equal(result.run_id, "run-123");
  assert.equal(result.operation_id, "company.enrich.profile");
  assert.equal(result.status, "found");
  assert.deepEqual(result.output, { company_name: "Acme" });
});

test("internal API client throws on HTTP error response", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        status: 500,
        body: {
          error: "boom",
        },
      },
    ]),
  });

  await assert.rejects(
    client.post("/api/internal/test", {}),
    (error: unknown) => error instanceof InternalApiError && error.message === "boom",
  );
});

test("internal API client surfaces timeout failures", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        error: timeoutError(),
      },
    ]),
  });

  await assert.rejects(
    client.post("/api/internal/test", {}, { timeoutMs: 50 }),
    (error: unknown) => error instanceof InternalApiTimeoutError,
  );
});
