import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import { recordStepTimelineEvent } from "../lineage.js";
import { createMockFetch } from "./test-helpers.js";

test("recordStepTimelineEvent posts timeline payload through internal API", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createMockFetch([
      {
        body: {
          data: {
            attempted: true,
            recorded: true,
          },
        },
      },
    ]),
  });

  const response = await recordStepTimelineEvent(client, {
    orgId: "org-1",
    companyId: "company-1",
    submissionId: "submission-1",
    pipelineRunId: "pipeline-1",
    entityType: "company",
    cumulativeContext: { company_domain: "acme.com" },
    stepResultId: "step-1",
    stepPosition: 1,
    operationId: "person.search",
    stepStatus: "succeeded",
    operationResult: {
      operation_id: "person.search",
      status: "found",
      output: { result_count: 1 },
    },
  });

  assert.equal(response.recorded, true);
});
