import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
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

test("pipeline router routes company enrichment and normalizes child step positions", async () => {
  const requests: CapturedRequest[] = [];
  const dispatchCalls: DispatchCall[] = [];
  const run = createBaseRun({
    blueprint_snapshot: {
      entity: {
        entity_type: "company",
        input: {
          company_domain: "acme.com",
          company_name: "Acme",
        },
      },
      fan_out: { start_from_position: 4 },
      steps: [
        { position: 4, operation_id: "company.enrich.profile", step_config: {} },
        { position: 5, operation_id: "company.research.infer_linkedin_url", step_config: {} },
      ],
    },
    step_results: [
      { id: "step-4", step_position: 4, status: "queued" },
      { id: "step-5", step_position: 5, status: "queued" },
    ],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "company-enrichment");
  assert.equal(result.used_fallback, false);
  assert.equal(dispatchCalls.length, 1);
  assert.equal(dispatchCalls[0]?.route, "companyEnrichment");
  assert.deepEqual((dispatchCalls[0]?.payload as { step_results: unknown }).step_results, [
    { step_result_id: "step-4", step_position: 1 },
    { step_result_id: "step-5", step_position: 2 },
  ]);
  assert.equal(
    (dispatchCalls[0]?.payload as { pipeline_run_id: string }).pipeline_run_id,
    "pipeline-1",
  );
  assert.equal(
    (dispatchCalls[0]?.payload as { company_domain: string }).company_domain,
    "acme.com",
  );
  assert.equal(
    requests[1]?.body?.trigger_run_id,
    "companyEnrichment-trigger-run",
  );
});

test("pipeline router falls back to run-pipeline for unsupported nested fan-out suffixes", async () => {
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
      fan_out: { start_from_position: 5 },
      steps: [
        { position: 5, operation_id: "person.search", fan_out: true, step_config: {} },
        { position: 6, operation_id: "person.contact.resolve_email", step_config: {} },
      ],
    },
    step_results: [
      { id: "step-5", step_position: 5, status: "queued" },
      { id: "step-6", step_position: 6, status: "queued" },
    ],
  });

  const result = await runPipelineRouter(baseRouterPayload(), {
    client: createClient(run, requests),
    dispatchers: createDispatchers(dispatchCalls),
  });

  assert.equal(result.route_key, "run-pipeline");
  assert.equal(result.used_fallback, true);
  assert.equal(dispatchCalls[0]?.route, "runPipeline");
  assert.deepEqual(dispatchCalls[0]?.payload, baseRouterPayload());
  assert.equal(requests[1]?.body?.trigger_run_id, "runPipeline-trigger-run");
});
