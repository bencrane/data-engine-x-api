import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
  __testables,
  PipelineRunRouterDispatchers,
  PipelineRunRouterPayload,
  runPipelineRouter,
} from "../pipeline-run-router.js";

type CapturedRequest = {
  path: string;
  body: Record<string, unknown> | null;
};

type DispatchCall = {
  route: keyof PipelineRunRouterDispatchers;
  payload: unknown;
  options: { idempotencyKey: string };
};

function createInternalFetch(params: {
  run: Record<string, unknown>;
  requests: CapturedRequest[];
}): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const body =
      typeof init?.body === "string"
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : null;

    params.requests.push({ path, body });

    if (path === "/api/internal/pipeline-runs/get") {
      return new Response(JSON.stringify({ data: params.run }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (path === "/api/internal/pipeline-runs/update-status") {
      return new Response(
        JSON.stringify({
          data: {
            id: body?.pipeline_run_id,
            status: body?.status,
            trigger_run_id: body?.trigger_run_id,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    throw new Error(`Unexpected internal fetch path: ${path}`);
  }) as typeof fetch;
}

function createClient(run: Record<string, unknown>, requests: CapturedRequest[]) {
  return createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createInternalFetch({ run, requests }),
  });
}

function createDispatchers(calls: DispatchCall[]): PipelineRunRouterDispatchers {
  const createDispatcher =
    (route: keyof PipelineRunRouterDispatchers) =>
    async (payload: unknown, options: { idempotencyKey: string }) => {
      calls.push({ route, payload, options });
      return { id: `${String(route)}-trigger-run` };
    };

  return {
    tamBuilding: createDispatcher("tamBuilding"),
    companyEnrichment: createDispatcher("companyEnrichment"),
    personSearchEnrichment: createDispatcher("personSearchEnrichment"),
    icpJobTitlesDiscovery: createDispatcher("icpJobTitlesDiscovery"),
    companyIntelBriefing: createDispatcher("companyIntelBriefing"),
    personIntelBriefing: createDispatcher("personIntelBriefing"),
    runPipeline: createDispatcher("runPipeline"),
  };
}

function createBaseRun(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: "pipeline-1",
    status: "queued",
    org_id: "org-1",
    company_id: "company-1",
    submission_id: "submission-1",
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          company_domain: "acme.com",
        },
      },
      steps: [],
    },
    step_results: [],
    ...overrides,
  };
}

function baseRouterPayload(): PipelineRunRouterPayload {
  return {
    pipeline_run_id: "pipeline-1",
    org_id: "org-1",
    company_id: "company-1",
    api_url: "https://example.com",
    internal_api_key: "secret",
  };
}

test("pipeline router routes person search enrichment and maps supported step config into payload", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          company_domain: "acme.com",
          client_company_name: "SellerCo",
        },
      },
      steps: [
        { position: 8, operation_id: "person.search", step_config: { limit: 12 } },
        { position: 9, operation_id: "person.enrich.profile", step_config: { include_work_history: true } },
        { position: 10, operation_id: "person.contact.resolve_email", step_config: {} },
      ],
    },
    step_results: [
      { id: "step-8", step_position: 8, status: "queued" },
      { id: "step-9", step_position: 9, status: "queued" },
      { id: "step-10", step_position: 10, status: "queued" },
    ],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "person-search-enrichment");
  assert.equal(dispatchCalls[0]?.route, "personSearchEnrichment");
  assert.equal((dispatchCalls[0]?.payload as { max_people: number }).max_people, 12);
  assert.equal(
    (dispatchCalls[0]?.payload as { include_work_history: boolean }).include_work_history,
    true,
  );
  assert.deepEqual((dispatchCalls[0]?.payload as { step_results: unknown }).step_results, [
    { step_result_id: "step-8", step_position: 1 },
    { step_result_id: "step-9", step_position: 2 },
    { step_result_id: "step-10", step_position: 3 },
  ]);
});

test("pipeline router routes TAM building and maps orchestration config into payload", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          keywords_include: ["sales intelligence"],
          hq_country_code: ["US"],
        },
      },
      steps: [
        {
          position: 4,
          operation_id: "company.search.blitzapi",
          step_config: {
            search_page_size: 50,
            company_batch_size: 12,
            poll_interval_ms: 500,
            person_max_people: 6,
            per_person_concurrency: 2,
            include_work_history: true,
          },
        },
      ],
    },
    step_results: [{ id: "step-4", step_position: 4, status: "queued" }],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "tam-building");
  assert.equal(dispatchCalls[0]?.route, "tamBuilding");
  assert.equal((dispatchCalls[0]?.payload as { search_page_size: number }).search_page_size, 50);
  assert.equal((dispatchCalls[0]?.payload as { company_batch_size: number }).company_batch_size, 12);
  assert.equal((dispatchCalls[0]?.payload as { poll_interval_ms: number }).poll_interval_ms, 500);
  assert.equal((dispatchCalls[0]?.payload as { person_max_people: number }).person_max_people, 6);
  assert.equal(
    (dispatchCalls[0]?.payload as { per_person_concurrency: number }).per_person_concurrency,
    2,
  );
  assert.equal(
    (dispatchCalls[0]?.payload as { include_work_history: boolean }).include_work_history,
    true,
  );
  assert.deepEqual((dispatchCalls[0]?.payload as { step_results: unknown }).step_results, [
    { step_result_id: "step-4", step_position: 1 },
  ]);
});

test("pipeline router routes ICP job titles discovery", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          domain: "acme.com",
          company_name: "Acme",
          company_description: "Procurement automation",
        },
      },
      steps: [{ position: 2, operation_id: "company.derive.icp_job_titles", step_config: { processor: "ultra" } }],
    },
    step_results: [{ id: "step-2", step_position: 2, status: "queued" }],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "icp-job-titles-discovery");
  assert.equal(dispatchCalls[0]?.route, "icpJobTitlesDiscovery");
  assert.equal((dispatchCalls[0]?.payload as { processor: string }).processor, "ultra");
  assert.equal(
    (dispatchCalls[0]?.payload as { company_description: string }).company_description,
    "Procurement automation",
  );
});

test("pipeline router routes company intel briefing", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          company_domain: "acme.com",
          company_name: "Acme",
          client_company_name: "SellerCo",
          client_company_domain: "sellerco.com",
          client_company_description: "SellerCo sells workflow software.",
          company_competitors: ["Rival One"],
        },
      },
      steps: [{ position: 1, operation_id: "company.derive.intel_briefing", step_config: { processor: "ultra" } }],
    },
    step_results: [{ id: "step-1", step_position: 1, status: "queued" }],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "company-intel-briefing");
  assert.equal(dispatchCalls[0]?.route, "companyIntelBriefing");
  assert.equal(
    (dispatchCalls[0]?.payload as { client_company_domain: string }).client_company_domain,
    "sellerco.com",
  );
  assert.deepEqual(
    (dispatchCalls[0]?.payload as { company_competitors: string[] }).company_competitors,
    ["Rival One"],
  );
});

test("pipeline router routes person intel briefing", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "person",
        input: {
          person_full_name: "Alex Doe",
          person_linkedin_url: "https://linkedin.com/in/alex",
          person_current_job_title: "VP Sales",
          person_current_company_name: "Acme",
          person_current_company_domain: "acme.com",
          client_company_name: "SellerCo",
          client_company_domain: "sellerco.com",
          client_company_description: "SellerCo sells workflow software.",
          customer_company_name: "CustomerCo",
          customer_company_domain: "customerco.com",
        },
      },
      steps: [{ position: 6, operation_id: "person.derive.intel_briefing", step_config: { processor: "pro" } }],
    },
    step_results: [{ id: "step-6", step_position: 6, status: "queued" }],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "person-intel-briefing");
  assert.equal(dispatchCalls[0]?.route, "personIntelBriefing");
  assert.equal(
    (dispatchCalls[0]?.payload as { customer_company_name: string }).customer_company_name,
    "CustomerCo",
  );
  assert.equal((dispatchCalls[0]?.payload as { processor: string }).processor, "pro");
});

test("pipeline router falls back to run-pipeline for unrecognized operation sequences", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          company_domain: "acme.com",
        },
      },
      steps: [{ position: 1, operation_id: "company.search", step_config: {} }],
    },
    step_results: [{ id: "step-1", step_position: 1, status: "queued" }],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "run-pipeline");
  assert.equal(result.used_fallback, true);
  assert.equal(dispatchCalls[0]?.route, "runPipeline");
});

test("route resolution is deterministic for the same DB-backed run payload", () => {
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          company_domain: "acme.com",
          client_company_name: "SellerCo",
          client_company_domain: "sellerco.com",
          client_company_description: "SellerCo sells workflow software.",
        },
      },
      steps: [{ position: 3, operation_id: "company.derive.intel_briefing", step_config: {} }],
    },
    step_results: [{ id: "step-3", step_position: 3, status: "queued" }],
  });

  const first = __testables.resolveDedicatedRoute(baseRouterPayload(), run as never);
  const second = __testables.resolveDedicatedRoute(baseRouterPayload(), run as never);

  assert.deepEqual(first, second);
  assert.equal(first?.routeKey, "company-intel-briefing");
});
