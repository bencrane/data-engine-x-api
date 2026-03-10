import assert from "node:assert/strict";
import test from "node:test";

import {
  ParallelDeepResearchError,
  runParallelDeepResearch,
} from "../parallel-deep-research.js";

type MockFetchResponse =
  | {
      status?: number;
      body?: unknown;
    }
  | {
      error: Error;
    };

type CapturedRequest = {
  url: string;
  method: string;
  body: Record<string, unknown> | null;
};

function createCapturingFetch(
  responses: MockFetchResponse[],
  requests: CapturedRequest[],
): typeof fetch {
  let index = 0;

  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const next = responses[index];
    index += 1;

    requests.push({
      url: String(input),
      method: init?.method ?? "GET",
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

test("runParallelDeepResearch applies staged polling intervals and returns extracted output", async () => {
  const requests: CapturedRequest[] = [];
  const delays: number[] = [];

  const result = await runParallelDeepResearch({
    prompt: "Research Acme",
    processor: "pro",
    operationId: "company.derive.icp_job_titles",
    providerAction: "deep_research_icp_job_titles",
    apiKey: "parallel-secret",
    fetchImpl: createCapturingFetch(
      [
        { body: { run_id: "parallel-run-1", status: "queued" } },
        { body: { status: "queued" } },
        { body: { status: "queued" } },
        { body: { status: "completed" } },
        {
          body: {
            output: {
              content: {
                inferredProduct: "Sales workflow software",
                titles: [{ title: "VP Sales", buyerRole: "decision_maker", reasoning: "Found in reviews" }],
              },
            },
          },
        },
      ],
      requests,
    ),
    sleep: async (delayMs) => {
      delays.push(delayMs);
    },
    pollingScheduleMs: [1_000, 2_000, 4_000],
    extractOutput: (resultPayload) => {
      const output = resultPayload.output;
      if (typeof output !== "object" || output === null || Array.isArray(output)) {
        throw new Error("missing output");
      }

      const content = (output as Record<string, unknown>).content;
      if (typeof content !== "object" || content === null || Array.isArray(content)) {
        throw new Error("missing content");
      }

      return content as Record<string, unknown>;
    },
  });

  assert.equal(result.parallelRunId, "parallel-run-1");
  assert.equal(result.pollCount, 3);
  assert.equal(result.elapsedMs, 7_000);
  assert.deepEqual(delays, [1_000, 2_000, 4_000]);
  assert.deepEqual(result.extractedOutput, {
    inferredProduct: "Sales workflow software",
    titles: [{ title: "VP Sales", buyerRole: "decision_maker", reasoning: "Found in reviews" }],
  });
  assert.equal(requests[0]?.method, "POST");
  assert.equal(requests[0]?.body?.processor, "pro");
  assert.equal(requests[4]?.url.endsWith("/v1/tasks/runs/parallel-run-1/result"), true);
});

test("runParallelDeepResearch times out when the staged schedule exceeds max wait", async () => {
  const delays: number[] = [];

  await assert.rejects(
    runParallelDeepResearch({
      prompt: "Research Acme",
      operationId: "company.derive.icp_job_titles",
      providerAction: "deep_research_icp_job_titles",
      apiKey: "parallel-secret",
      fetchImpl: createCapturingFetch([
        { body: { run_id: "parallel-run-1", status: "queued" } },
        { body: { status: "queued" } },
      ], []),
      sleep: async (delayMs) => {
        delays.push(delayMs);
      },
      pollingScheduleMs: [1_000, 1_500, 3_000],
      maxWaitMs: 2_000,
      extractOutput: () => ({ ok: true }),
    }),
    (error: unknown) =>
      error instanceof ParallelDeepResearchError &&
      error.phase === "status" &&
      /timed out/i.test(error.message),
  );

  assert.deepEqual(delays, [1_000]);
});

test("runParallelDeepResearch surfaces task creation HTTP failures", async () => {
  await assert.rejects(
    runParallelDeepResearch({
      prompt: "Research Acme",
      operationId: "company.derive.icp_job_titles",
      providerAction: "deep_research_icp_job_titles",
      apiKey: "parallel-secret",
      fetchImpl: createCapturingFetch([{ status: 500, body: { error: "boom" } }], []),
      extractOutput: () => ({ ok: true }),
    }),
    (error: unknown) =>
      error instanceof ParallelDeepResearchError &&
      error.phase === "create" &&
      error.statusCode === 500,
  );
});

test("runParallelDeepResearch surfaces polling HTTP failures", async () => {
  await assert.rejects(
    runParallelDeepResearch({
      prompt: "Research Acme",
      operationId: "company.derive.icp_job_titles",
      providerAction: "deep_research_icp_job_titles",
      apiKey: "parallel-secret",
      fetchImpl: createCapturingFetch(
        [
          { body: { run_id: "parallel-run-1", status: "queued" } },
          { status: 502, body: { error: "bad gateway" } },
        ],
        [],
      ),
      sleep: async () => {},
      pollingScheduleMs: [1_000],
      extractOutput: () => ({ ok: true }),
    }),
    (error: unknown) =>
      error instanceof ParallelDeepResearchError &&
      error.phase === "status" &&
      error.statusCode === 502,
  );
});

test("runParallelDeepResearch surfaces result-fetch HTTP failures", async () => {
  await assert.rejects(
    runParallelDeepResearch({
      prompt: "Research Acme",
      operationId: "company.derive.icp_job_titles",
      providerAction: "deep_research_icp_job_titles",
      apiKey: "parallel-secret",
      fetchImpl: createCapturingFetch(
        [
          { body: { run_id: "parallel-run-1", status: "completed" } },
          { status: 500, body: { error: "no result" } },
        ],
        [],
      ),
      extractOutput: () => ({ ok: true }),
    }),
    (error: unknown) =>
      error instanceof ParallelDeepResearchError &&
      error.phase === "result" &&
      error.statusCode === 500,
  );
});
