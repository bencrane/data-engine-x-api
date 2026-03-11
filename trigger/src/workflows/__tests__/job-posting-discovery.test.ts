import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import { runJobPostingDiscoveryWorkflow } from "../job-posting-discovery.js";

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
  entityUpsertResponses: RouteResponse[];
  requests: CapturedRequest[];
}) {
  const executeCounters = new Map<string, number>();
  const pipelineCounters = new Map<string, number>();
  let createChildrenIndex = 0;
  let entityUpsertIndex = 0;

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

    if (path === "/api/internal/entity-state/upsert") {
      const next = params.entityUpsertResponses[entityUpsertIndex];
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

    throw new Error(`Unexpected fetch path: ${path}`);
  }) as typeof fetch;
}

function createClient(params: {
  executeResponses: ExecuteResponseMap;
  pipelineRuns?: PipelineRunMap;
  createChildrenResponses?: CreateChildrenSequence;
  entityUpsertResponses?: RouteResponse[];
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
      entityUpsertResponses: params.entityUpsertResponses ?? [],
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
      posted_at_max_age_days: 7,
      job_title_or: ["sales engineer"],
      job_country_code_or: ["US"],
      discovered_at_gte: "2026-03-01T00:00:00Z",
      job_id_not: [999],
    },
    search_page_size: 2,
    company_batch_size: 10,
    poll_interval_ms: 1,
    per_person_concurrency: 2,
    page_retry_limit: 2,
  };
}

function buildJob(params: {
  id: number;
  title: string;
  companyName: string;
  companyDomain: string;
  companyLinkedinUrl: string;
  companyObjectId: string;
  url?: string;
}) {
  return {
    job_id: params.id,
    theirstack_job_id: params.id,
    job_title: params.title,
    normalized_title: params.title.toLowerCase(),
    company_name: params.companyName,
    company_domain: params.companyDomain,
    url: params.url ?? `https://jobs.example.com/${params.id}`,
    final_url: `https://careers.example.com/${params.id}`,
    source_url: `https://www.linkedin.com/jobs/view/${params.id}`,
    date_posted: "2026-03-09",
    discovered_at: "2026-03-10T00:00:00Z",
    remote: true,
    seniority: "mid_level",
    hiring_team: [
      {
        full_name: "Taylor Seller",
        first_name: "Taylor",
        linkedin_url: "https://www.linkedin.com/in/taylor-seller",
        role: "Hiring Manager",
      },
    ],
    company_object: {
      id: params.companyObjectId,
      name: params.companyName,
      domain: params.companyDomain,
      linkedin_url: params.companyLinkedinUrl,
      employee_count: 250,
      long_description: `${params.companyName} builds revenue software`,
      technology_slugs: ["salesforce", "postgresql"],
      industry: "software",
      funding_stage: "series_b",
      total_funding_usd: 25000000,
      annual_revenue_usd: 15000000,
      last_funding_round_date: "2025-10-01",
    },
  };
}

test("job posting discovery paginates via job.search, seeds child company runs from embedded company context, and preserves lineage", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "job.search": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "job.search",
              status: "found",
              output: {
                results: [
                  buildJob({
                    id: 101,
                    title: "Sales Engineer",
                    companyName: "Acme",
                    companyDomain: "acme.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/acme",
                    companyObjectId: "acme-co",
                  }),
                  buildJob({
                    id: 102,
                    title: "Solutions Consultant",
                    companyName: "Acme",
                    companyDomain: "acme.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/acme",
                    companyObjectId: "acme-co",
                  }),
                ],
                result_count: 2,
                source_provider: "theirstack",
              },
              provider_attempts: [{ provider: "theirstack", status: "found" }],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "search-2",
              operation_id: "job.search",
              status: "found",
              output: {
                results: [
                  buildJob({
                    id: 201,
                    title: "Account Executive",
                    companyName: "Beta",
                    companyDomain: "beta.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/beta",
                    companyObjectId: "beta-co",
                  }),
                ],
                result_count: 1,
                source_provider: "theirstack",
              },
              provider_attempts: [{ provider: "theirstack", status: "found" }],
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
              id: "company-step-1",
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
              id: "company-step-2",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "beta.com", company_name: "Beta" } },
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
              id: "person-step-1",
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
              id: "person-step-2",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "beta.com", people_persisted_count: 2 } },
            },
          ],
        },
      ],
    },
    entityUpsertResponses: [
      { body: { data: { entity_id: "job-entity-101" } } },
      { body: { data: { entity_id: "job-entity-102" } } },
      { body: { data: { entity_id: "job-entity-201" } } },
    ],
  });

  const result = await runJobPostingDiscoveryWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "succeeded");
  assert.equal(result.summary.pages_processed, 2);
  assert.equal(result.summary.jobs_discovered, 3);
  assert.equal(result.summary.unique_companies_discovered, 2);
  assert.equal(result.summary.company_runs_created, 2);
  assert.equal(result.summary.person_runs_created, 2);
  assert.equal(result.summary.job_entities_persisted, 3);
  assert.equal(result.job_results.length, 3);

  const job101 = result.job_results.find((job) => job.theirstack_job_id === 101);
  const job102 = result.job_results.find((job) => job.theirstack_job_id === 102);
  const job201 = result.job_results.find((job) => job.theirstack_job_id === 201);
  assert.equal(job101?.company_enrichment_pipeline_run_id, "company-run-1");
  assert.equal(job102?.company_enrichment_pipeline_run_id, "company-run-1");
  assert.equal(job101?.person_search_pipeline_run_id, "person-run-1");
  assert.equal(job102?.person_search_pipeline_run_id, "person-run-1");
  assert.equal(job201?.company_enrichment_pipeline_run_id, "company-run-2");
  assert.equal(job201?.person_search_pipeline_run_id, "person-run-2");
  assert.equal(job101?.job_entity_id, "job-entity-101");
  assert.equal(job102?.job_entity_id, "job-entity-102");
  assert.equal(job201?.job_entity_id, "job-entity-201");

  const executeRequests = requests.filter((request) => request.path === "/api/v1/execute");
  assert.equal(executeRequests.length, 2);
  assert.deepEqual(
    executeRequests.map((request) => request.body?.operation_id),
    ["job.search", "job.search"],
  );
  assert.equal(executeRequests[0]?.body?.entity_type, "job");
  assert.equal(
    (executeRequests[0]?.body?.input as { step_config?: Record<string, unknown> })?.step_config?.offset,
    0,
  );
  assert.equal(
    (executeRequests[1]?.body?.input as { step_config?: Record<string, unknown> })?.step_config?.offset,
    2,
  );

  const createChildrenRequests = requests.filter(
    (request) => request.path === "/api/internal/pipeline-runs/create-children",
  );
  assert.equal(createChildrenRequests.length, 3);
  assert.equal((createChildrenRequests[0]?.body?.child_entities as unknown[]).length, 2);
  const firstCompanySeed = (createChildrenRequests[0]?.body?.child_entities as Array<Record<string, unknown>>)[0];
  assert.equal(firstCompanySeed?.company_domain, "acme.com");
  assert.equal(firstCompanySeed?.company_linkedin_url, "https://www.linkedin.com/company/acme");
  assert.equal(firstCompanySeed?.theirstack_company_id, "acme-co");
  assert.equal(firstCompanySeed?.employee_count, 250);
  assert.equal(firstCompanySeed?.company_description, "Acme builds revenue software");

  const upsertRequests = requests.filter((request) => request.path === "/api/internal/entity-state/upsert");
  assert.equal(upsertRequests.length, 3);
  assert.equal(upsertRequests[0]?.body?.entity_type, "job");
  assert.equal(upsertRequests[0]?.body?.last_operation_id, "job.search");
});

test("job posting discovery retries HTTP 429 search pages and still returns the full result set", async () => {
  const requests: CapturedRequest[] = [];
  const sleepCalls: number[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "job.search": [
        {
          body: {
            data: {
              run_id: "search-retry-1",
              operation_id: "job.search",
              status: "failed",
              output: { results: [], result_count: 0 },
              provider_attempts: [{ provider: "theirstack", status: "failed", http_status: 429 }],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "search-retry-2",
              operation_id: "job.search",
              status: "found",
              output: {
                results: [
                  buildJob({
                    id: 301,
                    title: "Revenue Operations Manager",
                    companyName: "Gamma",
                    companyDomain: "gamma.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/gamma",
                    companyObjectId: "gamma-co",
                  }),
                ],
                result_count: 1,
              },
              provider_attempts: [{ provider: "theirstack", status: "found" }],
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
                pipeline_run_id: "company-run-gamma",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "gamma.com", company_name: "Gamma" },
              },
            ],
            child_run_ids: ["company-run-gamma"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-gamma",
            child_runs: [
              {
                pipeline_run_id: "person-run-gamma",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "gamma.com" },
              },
            ],
            child_run_ids: ["person-run-gamma"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
    ],
    pipelineRuns: {
      "company-run-gamma": [
        {
          id: "company-run-gamma",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "company-step-gamma",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "gamma.com", company_name: "Gamma" } },
            },
          ],
        },
      ],
      "person-run-gamma": [
        {
          id: "person-run-gamma",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "person-step-gamma",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "gamma.com" } },
            },
          ],
        },
      ],
    },
    entityUpsertResponses: [{ body: { data: { entity_id: "job-entity-301" } } }],
  });

  const result = await runJobPostingDiscoveryWorkflow(basePayload(), {
    client,
    sleep: async (ms) => {
      sleepCalls.push(ms);
    },
  });

  assert.equal(result.status, "succeeded");
  assert.equal(result.summary.pages_processed, 1);
  assert.equal(result.summary.jobs_discovered, 1);
  assert.equal(result.job_results[0]?.job_entity_id, "job-entity-301");
  assert.equal(sleepCalls.length, 1);
  assert.equal(sleepCalls[0], 1000);
  assert.equal(
    requests.filter((request) => request.path === "/api/v1/execute").length,
    2,
  );
});

test("job posting discovery fails on repeated later-page failures instead of silently truncating", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "job.search": [
        {
          body: {
            data: {
              run_id: "search-ok-1",
              operation_id: "job.search",
              status: "found",
              output: {
                results: [
                  buildJob({
                    id: 401,
                    title: "Sales Engineer",
                    companyName: "Acme",
                    companyDomain: "acme.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/acme",
                    companyObjectId: "acme-co",
                  }),
                  buildJob({
                    id: 402,
                    title: "Account Executive",
                    companyName: "Beta",
                    companyDomain: "beta.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/beta",
                    companyObjectId: "beta-co",
                  }),
                ],
                result_count: 2,
              },
              provider_attempts: [{ provider: "theirstack", status: "found" }],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "search-fail-1",
              operation_id: "job.search",
              status: "failed",
              output: { results: [], result_count: 0 },
              provider_attempts: [{ provider: "theirstack", status: "failed", http_status: 500 }],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "search-fail-2",
              operation_id: "job.search",
              status: "failed",
              output: { results: [], result_count: 0 },
              provider_attempts: [{ provider: "theirstack", status: "failed", http_status: 500 }],
            },
          },
        },
      ],
    },
    createChildrenResponses: [],
    entityUpsertResponses: [],
  });

  const result = await runJobPostingDiscoveryWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "failed");
  assert.match(result.error ?? "", /pagination failed/i);
  assert.equal(result.summary.pages_processed, 1);
  assert.equal(result.summary.jobs_discovered, 0);
  assert.equal(
    requests.filter((request) => request.path === "/api/internal/pipeline-runs/create-children").length,
    0,
  );
});

test("job posting discovery handles empty search results as a clean no-results outcome", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "job.search": [
        {
          body: {
            data: {
              run_id: "search-empty",
              operation_id: "job.search",
              status: "not_found",
              output: {
                results: [],
                result_count: 0,
              },
              provider_attempts: [{ provider: "theirstack", status: "not_found" }],
            },
          },
        },
      ],
    },
    createChildrenResponses: [],
    entityUpsertResponses: [],
  });

  const result = await runJobPostingDiscoveryWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "succeeded");
  assert.equal(result.summary.jobs_discovered, 0);
  assert.equal(result.summary.company_runs_created, 0);
  assert.equal(result.summary.person_runs_created, 0);
  assert.equal(result.summary.job_entities_persisted, 0);
  assert.equal(result.job_results.length, 0);
  assert.equal(
    requests.filter((request) => request.path === "/api/internal/pipeline-runs/create-children").length,
    0,
  );
  assert.equal(
    requests.filter((request) => request.path === "/api/internal/entity-state/upsert").length,
    0,
  );
});

test("job posting discovery fails when confirmed job persistence fails", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "job.search": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "job.search",
              status: "found",
              output: {
                results: [
                  buildJob({
                    id: 501,
                    title: "VP Sales",
                    companyName: "Delta",
                    companyDomain: "delta.com",
                    companyLinkedinUrl: "https://www.linkedin.com/company/delta",
                    companyObjectId: "delta-co",
                  }),
                ],
                result_count: 1,
              },
              provider_attempts: [{ provider: "theirstack", status: "found" }],
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
                pipeline_run_id: "company-run-delta",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "delta.com", company_name: "Delta" },
              },
            ],
            child_run_ids: ["company-run-delta"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
      {
        body: {
          data: {
            parent_pipeline_run_id: "company-run-delta",
            child_runs: [
              {
                pipeline_run_id: "person-run-delta",
                pipeline_run_status: "queued",
                entity_type: "company",
                entity_input: { company_domain: "delta.com" },
              },
            ],
            child_run_ids: ["person-run-delta"],
            skipped_duplicates_count: 0,
            skipped_duplicate_identifiers: [],
          },
        },
      },
    ],
    pipelineRuns: {
      "company-run-delta": [
        {
          id: "company-run-delta",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "company-step-delta",
              step_position: 2,
              output_payload: { cumulative_context: { company_domain: "delta.com", company_name: "Delta" } },
            },
          ],
        },
      ],
      "person-run-delta": [
        {
          id: "person-run-delta",
          submission_id: "submission-1",
          status: "succeeded",
          step_results: [
            {
              id: "person-step-delta",
              step_position: 3,
              output_payload: { cumulative_context: { company_domain: "delta.com" } },
            },
          ],
        },
      ],
    },
    entityUpsertResponses: [{ status: 500, body: { error: "job upsert exploded" } }],
  });

  const result = await runJobPostingDiscoveryWorkflow(basePayload(), {
    client,
    sleep: async () => {},
  });

  assert.equal(result.status, "failed");
  assert.match(result.error ?? "", /Entity state upsert failed/);
  assert.equal(result.summary.job_entities_persisted, 0);
  assert.equal(result.summary.job_entity_persistence_failed, 1);

  const pipelineStatusWrites = requests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatusWrites, ["running", "succeeded", "failed"]);

  const stepStatusWrites = requests
    .filter((request) => request.path === "/api/internal/step-results/update")
    .map((request) => request.body?.status);
  assert.deepEqual(stepStatusWrites, ["running", "succeeded", "failed"]);
});
