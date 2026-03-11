import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
  __testables,
  FMCSA_REVOCATION_DAILY_FEED,
  FMCSA_TOP5_DAILY_DIFF_FEEDS,
  runFmcsaDailyDiffWorkflow,
} from "../fmcsa-daily-diff.js";

type MockResponse =
  | {
      status?: number;
      body?: unknown;
    }
  | {
      error: Error;
    };

function createDownloadFetch(response: { status?: number; text: string } | { error: Error }): typeof fetch {
  return (async () => {
    if ("error" in response) {
      throw response.error;
    }

    return new Response(response.text, {
      status: response.status ?? 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }) as typeof fetch;
}

function createInternalFetch(params: {
  requests: Array<{ path: string; body: Record<string, unknown> | null }>;
  responses: MockResponse[];
}): typeof fetch {
  let index = 0;

  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname;
    const body =
      typeof init?.body === "string"
        ? (JSON.parse(init.body) as Record<string, unknown>)
        : null;

    params.requests.push({ path, body });

    const next = params.responses[index];
    index += 1;

    if (!next) {
      throw new Error(`Unexpected internal fetch call #${index}: ${path}`);
    }

    if ("error" in next) {
      throw next.error;
    }

    return new Response(JSON.stringify(next.body ?? { data: null }), {
      status: next.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
}

function createUnusedClient() {
  return createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createInternalFetch({ requests: [], responses: [] }),
  });
}

test("FMCSA daily diff workflow parses quoted no-header rows and confirms persistence", async () => {
  const internalRequests: Array<{ path: string; body: Record<string, unknown> | null }> = [];
  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createInternalFetch({
      requests: internalRequests,
      responses: [
        {
          body: {
            data: {
              feed_name: "Revocation",
              rows_received: 2,
              rows_written: 2,
            },
          },
        },
      ],
    }),
  });

  const result = await runFmcsaDailyDiffWorkflow(
    {
      feed: FMCSA_REVOCATION_DAILY_FEED,
      schedule: {
        timestamp: "2026-03-10T15:00:00.000Z",
        scheduleId: "schedule-1",
        timezone: "America/New_York",
      },
    },
    {
      client,
      fetchImpl: createDownloadFetch({
        text: [
          '"MC123456","12345678","Broker","03/08/2026","Insurance","03/10/2026"',
          '"FF222222","22223333","Common","03/09/2026","Safety","03/11/2026"',
        ].join("\n"),
      }),
    },
  );

  assert.equal(result.feed_name, "Revocation");
  assert.equal(result.rows_downloaded, 2);
  assert.equal(result.rows_parsed, 2);
  assert.equal(result.rows_accepted, 2);
  assert.equal(result.rows_rejected, 0);
  assert.equal(result.rows_written, 2);

  const request = internalRequests[0];
  assert.equal(request?.path, "/api/internal/operating-authority-revocations/upsert-batch");
  assert.equal(request?.body?.feed_name, "Revocation");
  assert.equal(request?.body?.source_file_variant, "daily diff");
  assert.equal((request?.body?.records as unknown[])?.length, 2);
});

test("FMCSA daily diff parser enforces row width for each top-5 feed", () => {
  for (const feed of FMCSA_TOP5_DAILY_DIFF_FEEDS) {
    const invalidRow = new Array(feed.expectedFieldCount - 1).fill('"x"').join(",");
    assert.throws(
      () => __testables.parseDailyDiffBody(feed, invalidRow),
      new RegExp(`expected ${feed.expectedFieldCount} columns`),
      feed.feedName,
    );
  }
});

test("FMCSA daily diff workflow fails on non-200 download responses", async () => {
  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      { feed: FMCSA_REVOCATION_DAILY_FEED },
      {
        client: createUnusedClient(),
        fetchImpl: createDownloadFetch({ status: 503, text: "unavailable" }),
      },
    ),
    /HTTP 503/,
  );
});

test("FMCSA daily diff workflow fails on empty download bodies", async () => {
  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      { feed: FMCSA_REVOCATION_DAILY_FEED },
      {
        client: createUnusedClient(),
        fetchImpl: createDownloadFetch({ text: "" }),
      },
    ),
    /empty body/i,
  );
});

test("FMCSA daily diff workflow fails on malformed CSV rows", async () => {
  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      { feed: FMCSA_REVOCATION_DAILY_FEED },
      {
        client: createUnusedClient(),
        fetchImpl: createDownloadFetch({
          text: '"MC123456","12345678","Broker","03/08/2026","Insurance","03/10/2026',
        }),
      },
    ),
    /CSV parsing failed/i,
  );
});

test("FMCSA daily diff workflow surfaces confirmed-write failures", async () => {
  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createInternalFetch({
      requests: [],
      responses: [
        {
          body: {
            data: {
              feed_name: "Revocation",
              rows_received: 0,
              rows_written: 0,
            },
          },
        },
      ],
    }),
  });

  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      { feed: FMCSA_REVOCATION_DAILY_FEED },
      {
        client,
        fetchImpl: createDownloadFetch({
          text: '"MC123456","12345678","Broker","03/08/2026","Insurance","03/10/2026"',
        }),
      },
    ),
    /could not be confirmed/i,
  );
});
