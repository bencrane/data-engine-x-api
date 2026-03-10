import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
  __testables,
  runIcpJobTitlesDiscoveryWorkflow,
} from "../icp-job-titles-discovery.js";

type CapturedRequest = {
  url: string;
  path: string;
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

function createInternalFetch(params: {
  entityUpsertResponses?: MockResponse[];
  icpUpsertResponses?: MockResponse[];
  requests: CapturedRequest[];
}): typeof fetch {
  let entityUpsertIndex = 0;
  let icpUpsertIndex = 0;

  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const body =
      typeof init?.body === "string"
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : null;

    params.requests.push({ url: String(input), path, body });

    if (path === "/api/internal/pipeline-runs/update-status") {
      return new Response(
        JSON.stringify({
          data: {
            id: body?.pipeline_run_id,
            status: body?.status,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    if (path === "/api/internal/step-results/update") {
      return new Response(
        JSON.stringify({
          data: {
            id: body?.step_result_id,
            step_position: 1,
            status: body?.status,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }

    if (path === "/api/internal/entity-state/upsert") {
      const next = params.entityUpsertResponses?.[entityUpsertIndex];
      entityUpsertIndex += 1;
      if (!next) {
        throw new Error(`Unexpected entity-state upsert #${entityUpsertIndex}`);
      }
      if ("error" in next) {
        throw next.error;
      }
      return new Response(JSON.stringify(next.body ?? { data: null }), {
        status: next.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (path === "/api/internal/icp-job-titles/upsert") {
      const next = params.icpUpsertResponses?.[icpUpsertIndex];
      icpUpsertIndex += 1;
      if (!next) {
        throw new Error(`Unexpected icp-job-titles upsert #${icpUpsertIndex}`);
      }
      if ("error" in next) {
        throw next.error;
      }
      return new Response(JSON.stringify(next.body ?? { data: null }), {
        status: next.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    throw new Error(`Unexpected internal fetch path: ${path}`);
  }) as typeof fetch;
}

function createParallelFetch(
  responses: MockResponse[],
  requests: CapturedRequest[],
): typeof fetch {
  let index = 0;

  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const next = responses[index];
    index += 1;

    const body =
      typeof init?.body === "string"
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : null;

    const url = String(input);
    requests.push({
      url,
      path: new URL(url).pathname,
      body,
    });

    if (!next) {
      throw new Error(`Unexpected parallel fetch #${index}`);
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

function createClient(params: {
  entityUpsertResponses?: MockResponse[];
  icpUpsertResponses?: MockResponse[];
  requests: CapturedRequest[];
}) {
  return createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createInternalFetch(params),
  });
}

function basePayload() {
  return {
    pipeline_run_id: "pipeline-1",
    org_id: "org-1",
    company_id: "company-1",
    company_domain: "acme.com",
    company_name: "Acme",
    company_description: "Acme sells workflow software for sales teams.",
    step_results: [{ step_result_id: "step-1", step_position: 1 }],
  };
}

test("ICP job titles discovery workflow completes the Parallel step and confirms both writes", async () => {
  const internalRequests: CapturedRequest[] = [];
  const parallelRequests: CapturedRequest[] = [];

  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [{ body: { data: { entity_id: "company-entity-1" } } }],
    icpUpsertResponses: [{ body: { data: { id: "icp-1", company_domain: "acme.com" } } }],
  });

  const result = await runIcpJobTitlesDiscoveryWorkflow(basePayload(), {
    client,
    parallelApiKey: "parallel-secret",
    parallelFetchImpl: createParallelFetch(
      [
        { body: { run_id: "parallel-run-1", status: "queued" } },
        { body: { status: "completed" } },
        {
          body: {
            output: {
              content: {
                inferredProduct: "Sales workflow software",
                buyerPersonaSummary: "Sales leaders champion, RevOps evaluates, CRO signs.",
                titles: [{ title: "VP Sales", buyerRole: "decision_maker", reasoning: "Seen in customer stories" }],
              },
            },
          },
        },
      ],
      parallelRequests,
    ),
    parallelSleep: async () => {},
  });

  assert.equal(result.status, "succeeded");
  assert.equal(result.entity_id, "company-entity-1");
  assert.equal(result.icp_job_titles_id, "icp-1");
  assert.equal(result.persistence.entity_state_confirmed, true);
  assert.equal(result.persistence.icp_job_titles_confirmed, true);
  assert.equal(result.cumulative_context.parallel_run_id, "parallel-run-1");
  assert.equal(result.cumulative_context.inferred_product, "Sales workflow software");

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["running", "succeeded"]);

  const stepStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/step-results/update")
    .map((request) => request.body?.status);
  assert.deepEqual(stepStatuses, ["running", "succeeded"]);

  const dedicatedWrite = internalRequests.find(
    (request) => request.path === "/api/internal/icp-job-titles/upsert",
  );
  assert.equal(dedicatedWrite?.body?.parallel_run_id, "parallel-run-1");
  assert.equal(
    (dedicatedWrite?.body?.raw_parallel_output as Record<string, unknown>)?.inferredProduct,
    "Sales workflow software",
  );

  assert.equal(parallelRequests.length, 3);
  assert.equal(parallelRequests[0]?.body?.processor, "pro");
});

test("ICP job titles discovery workflow surfaces entity-state write failures", async () => {
  const internalRequests: CapturedRequest[] = [];

  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [{ status: 500, body: { error: "entity blew up" } }],
    icpUpsertResponses: [{ body: { data: { id: "icp-1", company_domain: "acme.com" } } }],
  });

  const result = await runIcpJobTitlesDiscoveryWorkflow(basePayload(), {
    client,
    parallelApiKey: "parallel-secret",
    parallelFetchImpl: createParallelFetch(
      [
        { body: { run_id: "parallel-run-1", status: "completed" } },
        {
          body: {
            output: {
              content: {
                inferredProduct: "Sales workflow software",
                titles: [],
              },
            },
          },
        },
      ],
      [],
    ),
  });

  assert.equal(result.status, "failed");
  assert.equal(result.persistence.entity_state_confirmed, false);
  assert.equal(result.persistence.icp_job_titles_confirmed, true);
  assert.match(result.error ?? "", /Entity state upsert failed/);

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["running", "succeeded", "failed"]);
});

test("ICP job titles discovery workflow surfaces dedicated-table write failures", async () => {
  const internalRequests: CapturedRequest[] = [];

  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [{ body: { data: { entity_id: "company-entity-1" } } }],
    icpUpsertResponses: [{ status: 500, body: { error: "table blew up" } }],
  });

  const result = await runIcpJobTitlesDiscoveryWorkflow(basePayload(), {
    client,
    parallelApiKey: "parallel-secret",
    parallelFetchImpl: createParallelFetch(
      [
        { body: { run_id: "parallel-run-1", status: "completed" } },
        {
          body: {
            output: {
              content: {
                inferredProduct: "Sales workflow software",
                titles: [],
              },
            },
          },
        },
      ],
      [],
    ),
  });

  assert.equal(result.status, "failed");
  assert.equal(result.persistence.entity_state_confirmed, true);
  assert.equal(result.persistence.icp_job_titles_confirmed, false);
  assert.match(result.error ?? "", /ICP job titles upsert failed/);

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["running", "succeeded", "failed"]);
});

test("ICP job titles discovery workflow fails the step when Parallel result content is incomplete", async () => {
  const internalRequests: CapturedRequest[] = [];

  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [],
    icpUpsertResponses: [],
  });

  const result = await runIcpJobTitlesDiscoveryWorkflow(basePayload(), {
    client,
    parallelApiKey: "parallel-secret",
    parallelFetchImpl: createParallelFetch(
      [
        { body: { run_id: "parallel-run-1", status: "completed" } },
        {
          body: {
            output: {},
          },
        },
      ],
      [],
    ),
  });

  assert.equal(result.status, "failed");
  assert.match(result.error ?? "", /missing output\.content/i);

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["running", "failed"]);

  const stepStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/step-results/update")
    .map((request) => request.body?.status);
  assert.deepEqual(stepStatuses, ["running", "failed"]);

  assert.equal(
    internalRequests.some((request) => request.path === "/api/internal/entity-state/upsert"),
    false,
  );
  assert.equal(
    internalRequests.some((request) => request.path === "/api/internal/icp-job-titles/upsert"),
    false,
  );
});

test("ICP job titles discovery workflow validates the single expected step position", () => {
  assert.throws(
    () =>
      __testables.validateWorkflowStepReferences([
        { step_result_id: "step-1", step_position: 1 },
        { step_result_id: "step-2", step_position: 2 },
      ]),
    /requires 1 step_results/,
  );
});
