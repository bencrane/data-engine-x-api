import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
  PersistenceConfirmationError,
  upsertEntityStateConfirmed,
  writeDedicatedTableConfirmed,
} from "../persistence.js";
import { createMockFetch } from "./test-helpers.js";

test("upsertEntityStateConfirmed returns entity data when write is confirmed", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        body: {
          data: {
            entity_id: "entity-123",
            canonical_domain: "acme.com",
          },
        },
      },
    ]),
  });

  const result = await upsertEntityStateConfirmed(client, {
    pipelineRunId: "pipeline-1",
    entityType: "company",
    cumulativeContext: { company_domain: "acme.com" },
    lastOperationId: "company.enrich.profile",
  });

  assert.equal(result.entity_id, "entity-123");
});

test("upsertEntityStateConfirmed supports person entity writes", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        body: {
          data: {
            entity_id: "person-123",
            full_name: "Jane Doe",
          },
        },
      },
    ]),
  });

  const result = await upsertEntityStateConfirmed(client, {
    pipelineRunId: "pipeline-1",
    entityType: "person",
    cumulativeContext: {
      full_name: "Jane Doe",
      linkedin_url: "https://linkedin.com/in/jane-doe",
      work_email: "jane@acme.com",
    },
    lastOperationId: "person.contact.resolve_email",
  });

  assert.equal(result.entity_id, "person-123");
});

test("writeDedicatedTableConfirmed throws when response cannot be confirmed", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        body: {
          data: {
            recorded: false,
          },
        },
      },
    ]),
  });

  await assert.rejects(
    writeDedicatedTableConfirmed(client, {
      path: "/api/internal/company-customers/upsert",
      payload: { company_domain: "acme.com", customers: [] },
      validate: (response: { recorded?: boolean }) => response.recorded === true,
      confirmationErrorMessage: "Dedicated table write was not confirmed",
    }),
    (error: unknown) =>
      error instanceof PersistenceConfirmationError &&
      error.message === "Dedicated table write was not confirmed",
  );
});
