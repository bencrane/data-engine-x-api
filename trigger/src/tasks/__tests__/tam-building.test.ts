import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../../workflows/internal-api.js";
import { runTamBuildingWorkflow } from "../../workflows/tam-building.js";

type CapturedRequest = {
  path: string;
  body: Record<string, unknown> | null;
};

type RouteResponse =
  | {
      status?: number;
      body?: unknown;
    }
  | {
      error: Error;
    };

type ExecuteResponseMap = Record<string, RouteResponse[]>;
type PipelineRunMap = Record<string, Array<Record<string, unknown>>>;
type CreateChildrenSequence = Array<RouteResponse>;

function createRouteFetch(params: {
  executeResponses: ExecuteResponseMap;
  pipelineRuns: PipelineRunMap;
  createChildrenResponses: CreateChildrenSequence;
  requests: CapturedRequest[];
}) {
  const executeCounters = new Map<string, number>();
  const pipelineCounters = new Map<string, number>();
  let createChildrenIndex = 0;

  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const body =
      typeof init?.body === "string"
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : null;

    params.requests.push({ path, body });

    if (path === "/api/internal/pipeline-runs/update-status") {
      return new Response(
        JSON.stringify({
          data: {
            id: body?.pipeline_run_id,
            status: body?.status,
            trigger_run_id: body?.trigger_run_id,
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

    if (path === "/api/internal/entity-timeline/record-step-event") {
      return new Response(JSON.stringify({ data: { ok: true } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (path === "/api/internal/submissions/sync-status") {
      return new Response(JSON.stringify({ data: { id: body?.submission_id, status: "running" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (path === "/api/v1/execute") {
      const operationId = String(body?.operation_id ?? "");
      const responses = params.executeResponses[operationId] ?? [];
      const currentIndex = executeCounters.get(operationId) ?? 0;
      const next = responses[currentIndex];
      executeCounters.set(operationId, currentIndex + 1);

      if (!next) {
        throw new Error(`Unexpected execute response request for ${operationId} #${currentIndex + 1}`);
      }
      if ("error" in next) {
        throw next.error;
      }
      return new Response(JSON.stringify(next.body ?? { data: null }), {
        status: next.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (path === "/api/internal/pipeline-runs/create-children") {
      const next = params.createChildrenResponses[createChildrenIndex];
      createChildrenIndex += 1;

      if (!next) {
        throw new Error(`Unexpected create-children request #${createChildrenIndex}`);
      }
      if ("error" in next) {
        throw next.error;
      }
      return new Response(JSON.stringify(next.body ?? { data: null }), {
        status: next.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (path === "/api/internal/pipeline-runs/get") {
      const pipelineRunId = String(body?.pipeline_run_id ?? "");
      const responses = params.pipelineRuns[pipelineRunId] ?? [];
      const currentIndex = pipelineCounters.get(pipelineRunId) ?? 0;
      const next = responses[Math.min(currentIndex, Math.max(responses.length - 1, 0))];
      pipelineCounters.set(pipelineRunId, currentIndex + 1);

      if (!next) {
        throw new Error(`Unexpected pipeline-runs/get for ${pipelineRunId}`);
      }
      return new Response(JSON.stringify({ data: next }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    throw new Error(`Unexpected fetch path: ${path}`);
  }) as typeof fetch;
}

function createClient(params: {
  executeResponses: ExecuteResponseMap;
  pipelineRuns?: PipelineRunMap;
  createChildrenResponses?: CreateChildrenSequence;
  requests: CapturedRequest[];
}) {
  return createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createRouteFetch({
      executeResponses: params.executeResponses,
      pipelineRuns: params.pipelineRuns ?? {},
      createChildrenResponses: params.createChildrenResponses ?? [],
      requests: params.requests,
    }),
  });
}

function basePayload() {
  return {
    pipeline_run_id: "root-run-1",
    org_id: "org-1",
    company_id: "company-1",
    submission_id: "submission-1",
    step_results: [{ step_result_id: "root-step-1", step_position: 1 }],
    initial_context: {
      industry_include: ["IT Services and IT Consulting"],
      hq_country_code: ["US"],
    },
    search_page_size: 50,
    company_batch_size: 10,
    poll_interval_ms: 1,
    person_max_people: 5,
    per_person_concurrency: 2,
  };
}

test("tam building workflow paginates search results and creates company/person child runs", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "company.search.blitzapi": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "company.search.blitzapi",
              status: "found",
              output: {
                results: [
                  { company_domain: "acme.com", company_name: "Acme" },
                  { company_domain: "beta.com", company_name: "Beta" },
                ],
                results_count: 2,
                total_results: 3,
                cursor: "cursor-2",
                source_provider: "blitzapi",
              },
              provider_attempts: [],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "search-2",
              operation_id: "company.search.blitzapi",
              status: "found",
              output: {
                results: [{ company_domain: "gamma.com", company_name: "Gamma" }],
                results_count: 1,
                total_results: 3,
                cursor: null,
                source_provider: "blitzapi",
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    createChildrenResponses: [
      {
        body: {
          data: {
            parent_pipeline_run_id: "root-run-1",
            child_runs: [
              {
                pipeline_run_id: "company-run-1",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "acme.com", company_name: "Acme" },
              },
              {
                pipeline_run_id: "company-run-2",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "beta.com", company_name: "Beta" },
              },
              {
                pipeline_run_id: "company-run-3",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "gamma.com", company_name: "Gamma" },
              },
            ],
            child_run_ids: ["company-run-1", "company-run-2", "company-run-3"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-1",
            child_runs: [
              {
                pipeline_run_id: "person-run-1",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "acme.com" },
              },
            ],
            child_run_ids: ["person-run-1"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-2",
            child_runs: [
              {
                pipeline_run_id: "person-run-2",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "beta.com" },
              },
            ],
            child_run_ids: ["person-run-2"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-3",
            child_runs: [
              {
                pipeline_run_id: "person-run-3",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "gamma.com" },
              },
            ],
            child_run_ids: ["person-run-3"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
    ],
    pipelineRuns: {
      "company-run-1": [
        {
          id: "company-run-1",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-1",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "acme.com", company_name: "Acme" } },
            },
          ],
        },
      ],
      "company-run-2": [
        {
          id: "company-run-2",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-2",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "beta.com", company_name: "Beta" } },
            },
          ],
        },
      ],
      "company-run-3": [
        {
          id: "company-run-3",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-3",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "gamma.com", company_name: "Gamma" } },
            },
          ],
        },
      ],
      "person-run-1": [
        {
          id: "person-run-1",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-p1",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "acme.com", people_persisted_count: 4 } },
            },
          ],
        },
      ],
      "person-run-2": [
        {
          id: "person-run-2",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-p2",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "beta.com", people_persisted_count: 2 } },
            },
          ],
        },
      ],
      "person-run-3": [
        {
          id: "person-run-3",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-p3",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "gamma.com", people_persisted_count: 1 } },
            },
          ],
        },
      ],
    },
  });

  const result = await runTamBuildingWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "succeeded");
  assert.equal(result.summary.pages_processed, 2);
  assert.equal(result.summary.companies_discovered, 3);
  assert.equal(result.summary.company_runs_created, 3);
  assert.equal(result.summary.person_runs_created, 3);
  assert.equal(result.summary.person_runs_succeeded, 3);
  assert.equal(result.company_results.length, 3);
  assert.equal(result.company_results[0]?.company_enrichment_pipeline_run_id, "company-run-1");
  assert.equal(result.company_results[0]?.person_search_pipeline_run_id, "person-run-1");

  const createChildrenRequests = requests.filter(
    (request) => request.path === "/api/internal/pipeline-runs/create-children",
  );
  assert.equal(createChildrenRequests.length, 4);
  assert.equal((createChildrenRequests[0]?.body?.child_entities as unknown[]).length, 3);
});

test("tam building workflow records partial downstream failures without stopping the rest of the TAM build", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "company.search.blitzapi": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "company.search.blitzapi",
              status: "found",
              output: {
                results: [
                  { company_domain: "acme.com", company_name: "Acme" },
                  { company_domain: "beta.com", company_name: "Beta" },
                ],
                results_count: 2,
                total_results: 2,
                cursor: null,
                source_provider: "blitzapi",
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    createChildrenResponses: [
      {
        body: {
          data: {
            parent_pipeline_run_id: "root-run-1",
            child_runs: [
              {
                pipeline_run_id: "company-run-1",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "acme.com" },
              },
              {
                pipeline_run_id: "company-run-2",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "beta.com" },
              },
            ],
            child_run_ids: ["company-run-1", "company-run-2"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-1",
            child_runs: [
              {
                pipeline_run_id: "person-run-1",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "acme.com" },
              },
            ],
            child_run_ids: ["person-run-1"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-2",
            child_runs: [
              {
                pipeline_run_id: "person-run-2",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "beta.com" },
              },
            ],
            child_run_ids: ["person-run-2"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
    ],
    pipelineRuns: {
      "company-run-1": [
        {
          id: "company-run-1",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-1",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "acme.com" } },
            },
          ],
        },
      ],
      "company-run-2": [
        {
          id: "company-run-2",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-2",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "beta.com" } },
            },
          ],
        },
      ],
      "person-run-1": [
        {
          id: "person-run-1",
          submission_id: "submission-1",
          status: "failed",
          error_message: "email resolution failed",
          step_results: [
            {
              id: "step-p1",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "acme.com" } },
            },
          ],
        },
      ],
      "person-run-2": [
        {
          id: "person-run-2",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "step-p2",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "beta.com" } },
            },
          ],
        },
      ],
    },
  });

  const result = await runTamBuildingWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "failed");
  assert.equal(result.summary.person_runs_failed, 1);
  assert.equal(result.summary.person_runs_succeeded, 1);
  assert.equal(result.company_results.length, 2);
  assert.equal(result.company_results[0]?.person_search_status, "failed");
  assert.equal(result.company_results[1]?.person_search_status, "succeeded");

  const rootStepWrites = requests
    .filter((request) => request.path === "/api/internal/step-results/update")
    .map((request) => request.body?.status);
  assert.equal(rootStepWrites[rootStepWrites.length - 1], "failed");
});

test("tam building workflow handles empty search results cleanly", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "company.search.blitzapi": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "company.search.blitzapi",
              status: "not_found",
              output: {
                results: [],
                results_count: 0,
                total_results: 0,
                cursor: null,
                source_provider: "blitzapi",
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    createChildrenResponses: [],
    pipelineRuns: {},
  });

  const result = await runTamBuildingWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "succeeded");
  assert.equal(result.summary.companies_discovered, 0);
  assert.equal(result.summary.company_runs_created, 0);
  assert.equal(result.company_results.length, 0);
  assert.equal(
    requests.filter((request) => request.path === "/api/internal/pipeline-runs/create-children").length,
    0,
  );
});
