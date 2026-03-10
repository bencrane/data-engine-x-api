import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../../workflows/internal-api.js";
import {
  __testables,
  runPersonSearchEnrichmentWorkflow,
} from "../../workflows/person-search-enrichment.js";

type CapturedRequest = {
  path: string;
  body: Record<string, unknown> | null;
};

type MockRouteResponse =
  | {
      status?: number;
      body?: unknown;
    }
  | {
      error: Error;
    };

type ExecuteRouteMap = Record<string, MockRouteResponse[]>;

function createRouteFetch(params: {
  executeResponses: ExecuteRouteMap;
  entityUpsertResponses?: MockRouteResponse[];
  requests: CapturedRequest[];
}): typeof fetch {
  const executeCounters = new Map<string, number>();
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
            step_position: Number(body?.step_result_id?.toString().split("-")[1] ?? 0) || 0,
            status: body?.status,
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
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

    throw new Error(`Unexpected fetch path: ${path}`);
  }) as typeof fetch;
}

function createClient(params: {
  executeResponses: ExecuteRouteMap;
  entityUpsertResponses?: MockRouteResponse[];
  requests: CapturedRequest[];
}) {
  return createInternalApiClient({
    authContext: { orgId: "org-1", companyId: "company-1" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createRouteFetch(params),
  });
}

function basePayload() {
  return {
    pipeline_run_id: "pipeline-1",
    org_id: "org-1",
    company_id: "company-1",
    company_domain: "acme.com",
    step_results: [
      { step_result_id: "step-1", step_position: 1 },
      { step_result_id: "step-2", step_position: 2 },
      { step_result_id: "step-3", step_position: 3 },
    ],
  };
}

test("person search enrichment workflow discovers, enriches, and persists multiple people", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "person.search": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "person.search",
              status: "found",
              output: {
                results: [
                  {
                    full_name: "Jane Doe",
                    first_name: "Jane",
                    last_name: "Doe",
                    linkedin_url: "https://linkedin.com/in/jane-doe",
                    current_title: "VP Sales",
                    current_company_domain: "acme.com",
                    source_provider: "prospeo",
                    raw: {},
                  },
                  {
                    full_name: "John Roe",
                    first_name: "John",
                    last_name: "Roe",
                    current_title: "Director Marketing",
                    current_company_domain: "acme.com",
                    source_provider: "leadmagic",
                    raw: {},
                  },
                ],
                result_count: 2,
                provider_order_used: ["prospeo"],
                pagination: {},
              },
              provider_attempts: [],
            },
          },
        },
      ],
      "person.enrich.profile": [
        {
          body: {
            data: {
              run_id: "profile-1",
              operation_id: "person.enrich.profile",
              status: "found",
              output: {
                full_name: "Jane Doe",
                linkedin_url: "https://linkedin.com/in/jane-doe/",
                current_title: "VP Sales",
                department: "Sales",
                source_provider: "prospeo",
              },
              provider_attempts: [],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "profile-2",
              operation_id: "person.enrich.profile",
              status: "not_found",
              output: {},
              provider_attempts: [],
            },
          },
        },
      ],
      "person.contact.resolve_email": [
        {
          body: {
            data: {
              run_id: "email-1",
              operation_id: "person.contact.resolve_email",
              status: "found",
              output: {
                email: "jane@acme.com",
                verification: {
                  provider: "millionverifier",
                  status: "valid",
                  inconclusive: false,
                  raw_response: {},
                },
              },
              provider_attempts: [],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "email-2",
              operation_id: "person.contact.resolve_email",
              status: "not_found",
              output: {
                email: null,
                verification: null,
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    entityUpsertResponses: [
      { body: { data: { entity_id: "person-1" } } },
      { body: { data: { entity_id: "person-2" } } },
    ],
  });

  const result = await runPersonSearchEnrichmentWorkflow(basePayload(), { client });

  assert.equal(result.status, "succeeded");
  assert.equal(result.people_discovered, 2);
  assert.equal(result.people_persisted, 2);
  assert.equal(result.person_results.length, 2);
  assert.equal(result.person_results[0]?.entity_id, "person-1");
  assert.equal(result.person_results[0]?.work_email, "jane@acme.com");
  assert.equal(result.person_results[1]?.entity_id, "person-2");
  assert.equal(result.person_results[1]?.contact_status, "not_found");

  const executeRequests = requests.filter((request) => request.path === "/api/v1/execute");
  assert.equal(executeRequests.length, 5);

  const upsertRequests = requests.filter((request) => request.path === "/api/internal/entity-state/upsert");
  assert.equal(upsertRequests.length, 2);
  assert.equal(upsertRequests[0]?.body?.entity_type, "person");
  assert.equal(upsertRequests[0]?.body?.last_operation_id, "person.contact.resolve_email");
});

test("person search enrichment workflow isolates per-person provider failures", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "person.search": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "person.search",
              status: "found",
              output: {
                results: [
                  {
                    full_name: "Broken Person",
                    first_name: "Broken",
                    last_name: "Person",
                    current_company_domain: "acme.com",
                    source_provider: "prospeo",
                    raw: {},
                  },
                  {
                    full_name: "Healthy Person",
                    first_name: "Healthy",
                    last_name: "Person",
                    linkedin_url: "https://linkedin.com/in/healthy-person",
                    current_company_domain: "acme.com",
                    source_provider: "prospeo",
                    raw: {},
                  },
                ],
                result_count: 2,
                provider_order_used: ["prospeo"],
                pagination: {},
              },
              provider_attempts: [],
            },
          },
        },
      ],
      "person.enrich.profile": [
        { error: new Error("profile timeout") },
        {
          body: {
            data: {
              run_id: "profile-2",
              operation_id: "person.enrich.profile",
              status: "found",
              output: {
                full_name: "Healthy Person",
                linkedin_url: "https://linkedin.com/in/healthy-person",
                current_title: "Director Revenue Ops",
                source_provider: "prospeo",
              },
              provider_attempts: [],
            },
          },
        },
      ],
      "person.contact.resolve_email": [
        {
          body: {
            data: {
              run_id: "email-1",
              operation_id: "person.contact.resolve_email",
              status: "not_found",
              output: {
                email: null,
                verification: null,
              },
              provider_attempts: [],
            },
          },
        },
        {
          body: {
            data: {
              run_id: "email-2",
              operation_id: "person.contact.resolve_email",
              status: "found",
              output: {
                email: "healthy@acme.com",
                verification: {
                  provider: "millionverifier",
                  status: "valid",
                  inconclusive: false,
                  raw_response: {},
                },
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    entityUpsertResponses: [
      { body: { data: { entity_id: "person-broken" } } },
      { body: { data: { entity_id: "person-healthy" } } },
    ],
  });

  const result = await runPersonSearchEnrichmentWorkflow(basePayload(), { client });

  assert.equal(result.status, "succeeded");
  assert.equal(result.people_persisted, 2);
  assert.match((result.person_results[0]?.errors ?? []).join(","), /profile_transport/);
  assert.equal(result.person_results[1]?.work_email, "healthy@acme.com");
});

test("person search enrichment workflow fails when confirmed person persistence fails", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "person.search": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "person.search",
              status: "found",
              output: {
                results: [
                  {
                    full_name: "Jane Doe",
                    first_name: "Jane",
                    last_name: "Doe",
                    linkedin_url: "https://linkedin.com/in/jane-doe",
                    current_company_domain: "acme.com",
                    source_provider: "prospeo",
                    raw: {},
                  },
                ],
                result_count: 1,
                provider_order_used: ["prospeo"],
                pagination: {},
              },
              provider_attempts: [],
            },
          },
        },
      ],
      "person.enrich.profile": [
        {
          body: {
            data: {
              run_id: "profile-1",
              operation_id: "person.enrich.profile",
              status: "found",
              output: {
                full_name: "Jane Doe",
                linkedin_url: "https://linkedin.com/in/jane-doe",
                current_title: "VP Sales",
                source_provider: "prospeo",
              },
              provider_attempts: [],
            },
          },
        },
      ],
      "person.contact.resolve_email": [
        {
          body: {
            data: {
              run_id: "email-1",
              operation_id: "person.contact.resolve_email",
              status: "found",
              output: {
                email: "jane@acme.com",
                verification: {
                  provider: "millionverifier",
                  status: "valid",
                  inconclusive: false,
                  raw_response: {},
                },
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    entityUpsertResponses: [{ status: 500, body: { error: "upsert exploded" } }],
  });

  const result = await runPersonSearchEnrichmentWorkflow(basePayload(), { client });

  assert.equal(result.status, "failed");
  assert.match(result.error ?? "", /Entity state upsert failed/);

  const pipelineStatusWrites = requests
    .filter((request) => request.path === "/api/internal/pipeline-runs/update-status")
    .map((request) => request.body?.status);
  assert.deepEqual(pipelineStatusWrites, ["running", "failed"]);

  const stepWrites = requests.filter((request) => request.path === "/api/internal/step-results/update");
  const finalStepWrite = [...stepWrites].reverse().find((request) => request.body?.step_result_id === "step-3");
  assert.equal(finalStepWrite?.body?.status, "failed");
});

test("person search enrichment workflow skips enrichment phases when no people are discovered", async () => {
  const requests: CapturedRequest[] = [];
  const client = createClient({
    requests,
    executeResponses: {
      "person.search": [
        {
          body: {
            data: {
              run_id: "search-1",
              operation_id: "person.search",
              status: "not_found",
              output: {
                results: [],
                result_count: 0,
                provider_order_used: ["prospeo"],
                pagination: {},
              },
              provider_attempts: [],
            },
          },
        },
      ],
    },
    entityUpsertResponses: [],
  });

  const result = await runPersonSearchEnrichmentWorkflow(basePayload(), { client });

  assert.equal(result.status, "succeeded");
  assert.equal(result.people_discovered, 0);
  assert.equal(result.people_persisted, 0);
  assert.deepEqual(
    result.executed_steps.map((step) => step.status),
    ["succeeded", "skipped", "skipped"],
  );
});

test("person search enrichment workflow validates expected step positions", () => {
  assert.throws(
    () =>
      __testables.validateWorkflowStepReferences([
        { step_result_id: "step-1", step_position: 1 },
        { step_result_id: "step-2", step_position: 2 },
      ]),
    /requires 3 step_results/,
  );
});
