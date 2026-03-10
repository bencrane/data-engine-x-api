import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
  __testables,
  ParallelDeepResearchRunner,
  PersonIntelBriefingWorkflowPayload,
  runPersonIntelBriefingWorkflow,
} from "../person-intel-briefing.js";

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
  personIntelUpsertResponses?: MockResponse[];
  requests: CapturedRequest[];
}): typeof fetch {
  let entityUpsertIndex = 0;
  let personIntelUpsertIndex = 0;

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

    if (path === "/api/internal/person-intel-briefings/upsert") {
      const next = params.personIntelUpsertResponses?.[personIntelUpsertIndex];
      personIntelUpsertIndex += 1;
      if (!next) {
        throw new Error(`Unexpected person-intel-briefings upsert #${personIntelUpsertIndex}`);
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
  personIntelUpsertResponses?: MockResponse[];
  requests: CapturedRequest[];
}) {
  return createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createInternalFetch(params),
  });
}

function basePayload(): PersonIntelBriefingWorkflowPayload {
  return {
    pipeline_run_id: "pipeline-1",
    org_id: "org-1",
    company_id: "company-1",
    person_full_name: "Jane Doe",
    person_linkedin_url: "https://www.linkedin.com/in/jane-doe/",
    person_current_job_title: "VP of Security",
    person_current_company_name: "Acme",
    person_current_company_domain: "https://www.acme.com/security",
    person_current_company_description: "Acme builds procurement orchestration software.",
    client_company_name: "SellerCo",
    client_company_domain: "https://sellerco.com",
    client_company_description: "SellerCo sells security workflow automation.",
    customer_company_name: "BigBank",
    customer_company_domain: "bigbank.com",
    step_results: [{ step_result_id: "step-1", step_position: 1 }],
  };
}

function createStubParallelRunner(output: Record<string, unknown>): ParallelDeepResearchRunner {
  return async <TExtracted>() => ({
    parallelRunId: "parallel-run-1",
    processor: "pro",
    pollCount: 1,
    elapsedMs: 5_000,
    terminalStatus: "completed",
    rawResult: {
      output: {
        content: output,
      },
    },
    extractedOutput: output as TExtracted,
  });
}

test("person intel briefing workflow completes the Parallel step and confirms both writes", async () => {
  const internalRequests: CapturedRequest[] = [];
  const parallelRequests: CapturedRequest[] = [];

  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [{ body: { data: { entity_id: "person-entity-1" } } }],
    personIntelUpsertResponses: [
      {
        body: {
          data: {
            id: "briefing-1",
            person_full_name: "Jane Doe",
            person_linkedin_url: "https://www.linkedin.com/in/jane-doe",
            client_company_name: "SellerCo",
          },
        },
      },
    ],
  });

  const result = await runPersonIntelBriefingWorkflow(basePayload(), {
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
                executive_summary: "Jane Doe leads Acme's security program.",
                client_outreach_relevance: "SellerCo can help Jane reduce manual security reviews.",
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
  assert.equal(result.entity_id, "person-entity-1");
  assert.equal(result.person_intel_briefing_id, "briefing-1");
  assert.equal(result.persistence.entity_state_confirmed, true);
  assert.equal(result.persistence.person_intel_briefing_confirmed, true);
  assert.equal(result.cumulative_context.parallel_run_id, "parallel-run-1");
  assert.equal(result.cumulative_context.linkedin_url, "https://www.linkedin.com/in/jane-doe");
  assert.equal(result.cumulative_context.client_company_domain, "sellerco.com");
  assert.equal(result.cumulative_context.current_company_domain, "acme.com");

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["running", "succeeded"]);

  const stepStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/step-results/update")
    .map((request) => request.body?.status);
  assert.deepEqual(stepStatuses, ["running", "succeeded"]);

  const entityStateWrite = internalRequests.find(
    (request) => request.path === "/api/internal/entity-state/upsert",
  );
  assert.equal(entityStateWrite?.body?.entity_type, "person");
  assert.equal(
    (entityStateWrite?.body?.cumulative_context as Record<string, unknown>)?.linkedin_url,
    "https://www.linkedin.com/in/jane-doe",
  );

  const dedicatedWrite = internalRequests.find(
    (request) => request.path === "/api/internal/person-intel-briefings/upsert",
  );
  assert.equal(dedicatedWrite?.body?.parallel_run_id, "parallel-run-1");
  assert.equal(dedicatedWrite?.body?.person_linkedin_url, "https://www.linkedin.com/in/jane-doe");
  assert.equal(dedicatedWrite?.body?.client_company_name, "SellerCo");
  assert.equal(
    (dedicatedWrite?.body?.raw_parallel_output as Record<string, unknown>)?.executive_summary,
    "Jane Doe leads Acme's security program.",
  );
  assert.equal(dedicatedWrite?.body?.client_company_domain, undefined);

  assert.equal(parallelRequests.length, 3);
  assert.equal(parallelRequests[0]?.body?.processor, "pro");
});

test("person intel briefing workflow can delegate to an injected shared Parallel runner", async () => {
  const internalRequests: CapturedRequest[] = [];
  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [{ body: { data: { entity_id: "person-entity-1" } } }],
    personIntelUpsertResponses: [
      {
        body: {
          data: {
            id: "briefing-1",
            person_full_name: "Jane Doe",
            person_linkedin_url: "https://www.linkedin.com/in/jane-doe",
            client_company_name: "SellerCo",
          },
        },
      },
    ],
  });

  let runnerCalled = false;
  let capturedPrompt = "";
  const parallelRunner: ParallelDeepResearchRunner = async <TExtracted>(params: {
    prompt: string;
    processor?: string | null;
  }) => {
    runnerCalled = true;
    capturedPrompt = params.prompt;
    return {
      parallelRunId: "parallel-run-2",
      processor: String(params.processor),
      pollCount: 2,
      elapsedMs: 15_000,
      terminalStatus: "completed",
      rawResult: {
        output: {
          content: {
            client_outreach_relevance: "Jane Doe owns workflows SellerCo can improve.",
          },
        },
      },
      extractedOutput: {
        client_outreach_relevance: "Jane Doe owns workflows SellerCo can improve.",
      } as TExtracted,
    };
  };

  const result = await runPersonIntelBriefingWorkflow(basePayload(), {
    client,
    parallelRunner,
  });

  assert.equal(runnerCalled, true);
  assert.match(capturedPrompt, /client_company_domain: sellerco\.com/);
  assert.match(capturedPrompt, /person_linkedin_url: https:\/\/www\.linkedin\.com\/in\/jane-doe/);
  assert.equal(result.status, "succeeded");
  assert.equal(result.cumulative_context.parallel_run_id, "parallel-run-2");
});

test("person intel briefing workflow surfaces dedicated-table write failures", async () => {
  const internalRequests: CapturedRequest[] = [];
  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [{ body: { data: { entity_id: "person-entity-1" } } }],
    personIntelUpsertResponses: [{ status: 500, body: { error: "table blew up" } }],
  });

  const result = await runPersonIntelBriefingWorkflow(basePayload(), {
    client,
    parallelRunner: createStubParallelRunner({
      client_outreach_relevance: "Jane Doe is relevant.",
    }),
  });

  assert.equal(result.status, "failed");
  assert.equal(result.persistence.entity_state_confirmed, true);
  assert.equal(result.persistence.person_intel_briefing_confirmed, false);
  assert.match(result.error ?? "", /Person intel briefing upsert failed/);

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["running", "succeeded", "failed"]);
});

test("person intel briefing workflow fails explicitly when person identity is incomplete", async () => {
  const internalRequests: CapturedRequest[] = [];
  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [],
    personIntelUpsertResponses: [],
  });

  const payload = {
    ...basePayload(),
    person_linkedin_url: "   ",
    person_current_job_title: "   ",
  };

  const result = await runPersonIntelBriefingWorkflow(payload, {
    client,
  });

  assert.equal(result.status, "failed");
  assert.match(result.error ?? "", /person_linkedin_url or person_current_job_title is required/);
  assert.equal(
    internalRequests.some((request) => request.path === "/api/internal/step-results/update"),
    false,
  );

  const pipelineStatuses = internalRequests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatuses, ["failed"]);
});

test("person intel briefing workflow fails the step when Parallel result content is incomplete", async () => {
  const internalRequests: CapturedRequest[] = [];
  const client = createClient({
    requests: internalRequests,
    entityUpsertResponses: [],
    personIntelUpsertResponses: [],
  });

  const result = await runPersonIntelBriefingWorkflow(basePayload(), {
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
});

test("person intel briefing workflow validates the single expected step position", () => {
  assert.throws(
    () =>
      __testables.validateWorkflowStepReferences([
        { step_result_id: "step-1", step_position: 1 },
        { step_result_id: "step-2", step_position: 2 },
      ]),
    /requires 1 step_results/,
  );
});
