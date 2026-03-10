import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../../workflows/internal-api.js";
import { runCompanyEnrichmentWorkflow } from "../../workflows/company-enrichment.js";

type CapturedRequest = {
  url: string;
  body: Record<string, unknown> | null;
};

type MockResponse =
  | {
      status?: number;
      body?: unknown;
    }
  | {
      error: Error;
    };

function createCapturingFetch(
  responses: MockResponse[],
  requests: CapturedRequest[],
): typeof fetch {
  let index = 0;

  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const next = responses[index];
    index += 1;

    requests.push({
      url: String(input),
      body:
        typeof init?.body === "string"
          ? (JSON.parse(init.body) as Record<string, unknown>)
          : null,
    });

    if (!next) {
      throw new Error(`Unexpected fetch call #${index}`);
    }

    if ("error" in next) {
      throw next.error;
    }

    return new Response(next.body === undefined ? null : JSON.stringify(next.body), {
      status: next.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
}

function createClient(responses: MockResponse[], requests: CapturedRequest[]) {
  return createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createCapturingFetch(responses, requests),
  });
}

function getExecuteInput(request: CapturedRequest): Record<string, unknown> {
  const input = request.body?.input;
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    return {};
  }
  return input as Record<string, unknown>;
}

test("company enrichment workflow executes steps in order and merges context", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient(
    [
      { body: { data: { id: "pipeline-1", status: "running" } } },
      { body: { data: { id: "step-1", step_position: 1, status: "running" } } },
      {
        body: {
          data: {
            run_id: "run-1",
            operation_id: "company.enrich.profile",
            status: "found",
            output: {
              company_name: "Acme",
              employee_count: 120,
            },
            provider_attempts: [],
          },
        },
      },
      { body: { data: { id: "step-1", step_position: 1, status: "succeeded" } } },
      { body: { data: { id: "step-2", step_position: 2, status: "running" } } },
      {
        body: {
          data: {
            run_id: "run-2",
            operation_id: "company.research.infer_linkedin_url",
            status: "found",
            output: {
              linkedin_url: "https://linkedin.com/company/acme",
            },
            provider_attempts: [],
          },
        },
      },
      { body: { data: { id: "step-2", step_position: 2, status: "succeeded" } } },
      { body: { data: { id: "pipeline-1", status: "succeeded" } } },
      { body: { data: { entity_id: "entity-1" } } },
    ],
    requests,
  );

  const result = await runCompanyEnrichmentWorkflow(
    {
      pipeline_run_id: "pipeline-1",
      org_id: "org-1",
      company_id: "company-1",
      company_domain: "acme.com",
      step_results: [
        { step_result_id: "step-1", step_position: 1 },
        { step_result_id: "step-2", step_position: 2 },
      ],
    },
    { client },
  );

  assert.equal(result.status, "succeeded");
  assert.equal(result.entity_id, "entity-1");
  assert.equal(result.cumulative_context.company_name, "Acme");
  assert.equal(result.cumulative_context.employee_count, 120);
  assert.equal(result.cumulative_context.linkedin_url, "https://linkedin.com/company/acme");

  const executeRequests = requests.filter((request) => request.url.endsWith("/api/v1/execute"));
  assert.equal(executeRequests.length, 2);
  assert.equal(executeRequests[0]?.body?.operation_id, "company.enrich.profile");
  assert.equal(executeRequests[1]?.body?.operation_id, "company.research.infer_linkedin_url");
  assert.equal(getExecuteInput(executeRequests[1]!).company_name, "Acme");
  assert.equal(getExecuteInput(executeRequests[1]!).employee_count, 120);
});

test("company enrichment workflow skips linkedin inference when already present", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient(
    [
      { body: { data: { id: "pipeline-1", status: "running" } } },
      { body: { data: { id: "step-1", step_position: 1, status: "running" } } },
      {
        body: {
          data: {
            run_id: "run-1",
            operation_id: "company.enrich.profile",
            status: "found",
            output: {
              company_name: "Acme",
              linkedin_url: "https://linkedin.com/company/acme",
            },
            provider_attempts: [],
          },
        },
      },
      { body: { data: { id: "step-1", step_position: 1, status: "succeeded" } } },
      { body: { data: { id: "step-2", step_position: 2, status: "skipped" } } },
      { body: { data: { id: "pipeline-1", status: "succeeded" } } },
      { body: { data: { entity_id: "entity-1" } } },
    ],
    requests,
  );

  const result = await runCompanyEnrichmentWorkflow(
    {
      pipeline_run_id: "pipeline-1",
      org_id: "org-1",
      company_id: "company-1",
      company_domain: "acme.com",
      step_results: [
        { step_result_id: "step-1", step_position: 1 },
        { step_result_id: "step-2", step_position: 2 },
      ],
    },
    { client },
  );

  assert.equal(result.status, "succeeded");
  assert.equal(result.executed_steps[1]?.status, "skipped");
  assert.equal(requests.filter((request) => request.url.endsWith("/api/v1/execute")).length, 1);
});

test("company enrichment workflow surfaces entity-state persistence failure", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient(
    [
      { body: { data: { id: "pipeline-1", status: "running" } } },
      { body: { data: { id: "step-1", step_position: 1, status: "running" } } },
      {
        body: {
          data: {
            run_id: "run-1",
            operation_id: "company.enrich.profile",
            status: "found",
            output: {
              company_name: "Acme",
            },
            provider_attempts: [],
          },
        },
      },
      { body: { data: { id: "step-1", step_position: 1, status: "succeeded" } } },
      { body: { data: { id: "step-2", step_position: 2, status: "running" } } },
      {
        body: {
          data: {
            run_id: "run-2",
            operation_id: "company.research.infer_linkedin_url",
            status: "not_found",
            output: {},
            provider_attempts: [],
          },
        },
      },
      { body: { data: { id: "step-2", step_position: 2, status: "succeeded" } } },
      { body: { data: { id: "pipeline-1", status: "succeeded" } } },
      { status: 500, body: { error: "invalid" } },
      { body: { data: { id: "pipeline-1", status: "failed" } } },
    ],
    requests,
  );

  const result = await runCompanyEnrichmentWorkflow(
    {
      pipeline_run_id: "pipeline-1",
      org_id: "org-1",
      company_id: "company-1",
      company_domain: "acme.com",
      step_results: [
        { step_result_id: "step-1", step_position: 1 },
        { step_result_id: "step-2", step_position: 2 },
      ],
    },
    { client },
  );

  assert.equal(result.status, "failed");
  assert.match(result.error ?? "", /Entity state upsert failed/);

  const pipelineStatusWrites = requests
    .filter((request) => request.url.endsWith("/api/internal/pipeline-runs/update-status"))
    .map((request) => request.body?.status);

  assert.deepEqual(pipelineStatusWrites, ["running", "succeeded", "failed"]);
});
