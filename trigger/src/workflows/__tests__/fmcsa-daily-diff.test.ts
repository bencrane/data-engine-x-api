import assert from "node:assert/strict";
import test from "node:test";

import { createInternalApiClient } from "../internal-api.js";
import {
  __testables,
  FMCSA_CARRIER_ALL_HISTORY_CSV_FEED,
  FMCSA_COMPANY_CENSUS_FILE_FEED,
  FMCSA_CRASH_FILE_FEED,
  FMCSA_INSPECTIONS_AND_CITATIONS_FEED,
  FMCSA_INSPECTIONS_PER_UNIT_FEED,
  FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
  FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
  FMCSA_REMAINING_CSV_EXPORT_FEEDS,
  FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED,
  FMCSA_SPECIAL_STUDIES_FEED,
  FMCSA_VEHICLE_INSPECTION_FILE_FEED,
  FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED,
  FMCSA_SMS_AB_PASS_FEED,
  FMCSA_SMS_AB_PASSPROPERTY_FEED,
  FMCSA_SMS_C_PASS_FEED,
  FMCSA_SMS_C_PASSPROPERTY_FEED,
  FMCSA_SMS_FEEDS,
  FMCSA_SMS_FEED_CORRECTIONS,
  FMCSA_SMS_INPUT_INSPECTION_FEED,
  FMCSA_SMS_INPUT_VIOLATION_FEED,
  FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED,
  FMCSA_SMS_SKIPPED_FEEDS,
  FMCSA_AUTHHIST_ALL_HISTORY_FEED,
  FMCSA_BOC3_DAILY_FEED,
  FMCSA_CARRIER_DAILY_FEED,
  FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS,
  FMCSA_REJECTED_ALL_HISTORY_FEED,
  FMCSA_REJECTED_DAILY_FEED,
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

function createDownloadFetch(
  response: { status?: number; text: string; contentType?: string } | { error: Error },
): typeof fetch {
  return (async () => {
    if ("error" in response) {
      throw response.error;
    }

    return new Response(response.text, {
      status: response.status ?? 200,
      headers: { "Content-Type": response.contentType ?? "text/plain; charset=utf-8" },
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
              feed_date: "2026-03-10",
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
  assert.equal(result.feed_date, "2026-03-10");
  assert.equal(result.source_file_variant, "daily diff");
  assert.equal(result.rows_downloaded, 2);
  assert.equal(result.rows_parsed, 2);
  assert.equal(result.rows_accepted, 2);
  assert.equal(result.rows_rejected, 0);
  assert.equal(result.rows_written, 2);

  const request = internalRequests[0];
  assert.equal(request?.path, "/api/internal/operating-authority-revocations/upsert-batch");
  assert.equal(request?.body?.feed_name, "Revocation");
  assert.equal(request?.body?.feed_date, "2026-03-10");
  assert.equal(request?.body?.source_file_variant, "daily diff");
  assert.equal((request?.body?.records as unknown[])?.length, 2);
});

test("next-batch feed configs lock dictionary widths and shared-table mappings", () => {
  assert.deepEqual(
    FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      sourceFileVariant: feed.sourceFileVariant,
      expectedFieldCount: feed.expectedFieldCount,
      internalUpsertPath: feed.internalUpsertPath,
    })),
    [
      {
        feedName: "Carrier",
        sourceFileVariant: "daily",
        expectedFieldCount: 43,
        internalUpsertPath: "/api/internal/carrier-registrations/upsert-batch",
      },
      {
        feedName: "Rejected",
        sourceFileVariant: "daily",
        expectedFieldCount: 15,
        internalUpsertPath: "/api/internal/insurance-filing-rejections/upsert-batch",
      },
      {
        feedName: "BOC3",
        sourceFileVariant: "daily",
        expectedFieldCount: 9,
        internalUpsertPath: "/api/internal/process-agent-filings/upsert-batch",
      },
      {
        feedName: "InsHist - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 17,
        internalUpsertPath: "/api/internal/insurance-policy-history-events/upsert-batch",
      },
      {
        feedName: "BOC3 - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 9,
        internalUpsertPath: "/api/internal/process-agent-filings/upsert-batch",
      },
      {
        feedName: "ActPendInsur - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 11,
        internalUpsertPath: "/api/internal/insurance-policy-filings/upsert-batch",
      },
      {
        feedName: "Rejected - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 15,
        internalUpsertPath: "/api/internal/insurance-filing-rejections/upsert-batch",
      },
      {
        feedName: "AuthHist - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 9,
        internalUpsertPath: "/api/internal/operating-authority-histories/upsert-batch",
      },
    ],
  );
});

test("shared-table variants remain distinct by source feed metadata", async () => {
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
              feed_name: "Rejected - All With History",
              feed_date: "2026-03-10",
              rows_received: 1,
              rows_written: 1,
            },
          },
        },
      ],
    }),
  });

  const result = await runFmcsaDailyDiffWorkflow(
    {
      feed: FMCSA_REJECTED_ALL_HISTORY_FEED,
      schedule: {
        timestamp: "2026-03-10T16:00:00.000Z",
        scheduleId: "schedule-history",
        timezone: "America/New_York",
      },
    },
    {
      client,
      fetchImpl: createDownloadFetch({
        text: '"MC123456","12345678","82","BI&PD","POL-1","03/01/2026","P"," ","0","750","03/02/2026","01","ACME INSURANCE","Missing signature","750"',
      }),
    },
  );

  assert.equal(result.source_file_variant, "all_with_history");
  const request = internalRequests[0];
  assert.equal(request?.path, "/api/internal/insurance-filing-rejections/upsert-batch");
  assert.equal(request?.body?.feed_name, "Rejected - All With History");
  assert.equal(request?.body?.source_file_variant, "all_with_history");
});

test("remaining CSV export feed configs lock widths and endpoint paths", () => {
  assert.deepEqual(
    FMCSA_REMAINING_CSV_EXPORT_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      sourceFileVariant: feed.sourceFileVariant,
      expectedFieldCount: feed.expectedFieldCount,
      internalUpsertPath: feed.internalUpsertPath,
      useStreamingParser: feed.useStreamingParser ?? false,
    })),
    [
      {
        feedName: "Crash File",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 59,
        internalUpsertPath: "/api/internal/commercial-vehicle-crashes/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Carrier - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 43,
        internalUpsertPath: "/api/internal/carrier-registrations/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Inspections Per Unit",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 12,
        internalUpsertPath: "/api/internal/vehicle-inspection-units/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Special Studies",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 5,
        internalUpsertPath: "/api/internal/vehicle-inspection-special-studies/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Revocation - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 6,
        internalUpsertPath: "/api/internal/operating-authority-revocations/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Insur - All With History",
        sourceFileVariant: "all_with_history",
        expectedFieldCount: 9,
        internalUpsertPath: "/api/internal/insurance-policies/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "OUT OF SERVICE ORDERS",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 7,
        internalUpsertPath: "/api/internal/out-of-service-orders/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Inspections and Citations",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 6,
        internalUpsertPath: "/api/internal/vehicle-inspection-citations/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Vehicle Inspections and Violations",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 12,
        internalUpsertPath: "/api/internal/carrier-inspection-violations/upsert-batch",
        useStreamingParser: false,
      },
      {
        feedName: "Company Census File",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 147,
        internalUpsertPath: "/api/internal/motor-carrier-census-records/upsert-batch",
        useStreamingParser: true,
      },
      {
        feedName: "Vehicle Inspection File",
        sourceFileVariant: "csv_export",
        expectedFieldCount: 63,
        internalUpsertPath: "/api/internal/carrier-inspections/upsert-batch",
        useStreamingParser: true,
      },
    ],
  );
});

test("remaining CSV export workflow maps aliased headers onto dictionary fields", async () => {
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
              feed_name: "OUT OF SERVICE ORDERS",
              feed_date: "2026-03-10",
              rows_received: 1,
              rows_written: 1,
            },
          },
        },
      ],
    }),
  });

  await runFmcsaDailyDiffWorkflow(
    {
      feed: FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
      schedule: {
        timestamp: "2026-03-10T16:00:00.000Z",
        scheduleId: "schedule-oos",
        timezone: "America/New_York",
      },
    },
    {
      client,
      fetchImpl: createDownloadFetch({
        contentType: "text/csv; charset=utf-8",
        text: [
          "DOT_NUMBER,LEGAL_NAME,DBA_NAME,OOS_DATE,OOS_REASON,STATUS,RESCIND_DATE",
          "1438,AUSTIN URETHANE INC,,2022-07-09,Unsatisfactory = Unfit,ACTIVE,2022-08-01",
        ].join("\n"),
      }),
    },
  );

  const request = internalRequests[0];
  const firstRecord = ((request?.body?.records as Array<Record<string, unknown>>) ?? [])[0];
  const rawFields = (firstRecord?.raw_fields as Record<string, unknown>) ?? {};
  assert.equal(request?.path, "/api/internal/out-of-service-orders/upsert-batch");
  assert.equal(rawFields.OOS_RESCIND_DATE, "2022-08-01");
});

test("remaining CSV export parser enforces representative row widths", () => {
  for (const feed of [
    FMCSA_CRASH_FILE_FEED,
    FMCSA_CARRIER_ALL_HISTORY_CSV_FEED,
    FMCSA_INSPECTIONS_PER_UNIT_FEED,
    FMCSA_SPECIAL_STUDIES_FEED,
    FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED,
    FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
    FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
    FMCSA_INSPECTIONS_AND_CITATIONS_FEED,
    FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED,
  ]) {
    const invalidCsv = [feed.headerRow?.join(",") ?? "", "x"].join("\n");
    assert.throws(
      () => __testables.parseDailyDiffBody(feed, invalidCsv),
      new RegExp(`expected ${feed.expectedFieldCount} columns`),
      feed.feedName,
    );
  }
});

test("remaining CSV export workflow streams large files in multiple confirmed batches", async () => {
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
              feed_name: "Company Census File",
              feed_date: "2026-03-10",
              rows_received: 2,
              rows_written: 2,
            },
          },
        },
        {
          body: {
            data: {
              feed_name: "Company Census File",
              feed_date: "2026-03-10",
              rows_received: 1,
              rows_written: 1,
            },
          },
        },
      ],
    }),
  });

  const header = FMCSA_COMPANY_CENSUS_FILE_FEED.headerRow?.join(",") ?? "";
  const row = new Array(FMCSA_COMPANY_CENSUS_FILE_FEED.expectedFieldCount).fill("").map((_, index) => {
    if (index === 3) return "123456";
    if (index === 52) return "ACME LOGISTICS LLC";
    return "";
  });

  const result = await runFmcsaDailyDiffWorkflow(
    {
      feed: {
        ...FMCSA_COMPANY_CENSUS_FILE_FEED,
        writeBatchSize: 2,
      },
      schedule: {
        timestamp: "2026-03-10T16:00:00.000Z",
        scheduleId: "schedule-company-census",
        timezone: "America/New_York",
      },
    },
    {
      client,
      fetchImpl: createDownloadFetch({
        contentType: "text/csv; charset=utf-8",
        text: [header, row.join(","), row.join(","), row.join(",")].join("\n"),
      }),
    },
  );

  assert.equal(result.rows_downloaded, 3);
  assert.equal(result.rows_written, 3);
  assert.equal(internalRequests.length, 2);
  assert.equal(
    ((internalRequests[0]?.body?.records as Array<unknown>) ?? []).length,
    2,
  );
  assert.equal(
    ((internalRequests[1]?.body?.records as Array<unknown>) ?? []).length,
    1,
  );
});

test("SMS feed configs lock corrected dataset ids and crash skip metadata", () => {
  assert.deepEqual(
    FMCSA_SMS_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      taskId: feed.taskId,
      downloadUrl: feed.downloadUrl,
      expectedFieldCount: feed.expectedFieldCount,
      sourceFileVariant: feed.sourceFileVariant,
    })),
    [
      {
        feedName: "SMS AB PassProperty",
        taskId: "fmcsa-sms-ab-passproperty-daily",
        downloadUrl: "https://data.transportation.gov/api/views/4y6x-dmck/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 21,
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS C PassProperty",
        taskId: "fmcsa-sms-c-passproperty-daily",
        downloadUrl: "https://data.transportation.gov/api/views/h9zy-gjn8/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 21,
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS Input - Violation",
        taskId: "fmcsa-sms-input-violation-daily",
        downloadUrl: "https://data.transportation.gov/api/views/8mt8-2mdr/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 13,
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS Input - Inspection",
        taskId: "fmcsa-sms-input-inspection-daily",
        downloadUrl: "https://data.transportation.gov/api/views/rbkj-cgst/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 39,
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS Input - Motor Carrier Census",
        taskId: "fmcsa-sms-motor-carrier-census-daily",
        downloadUrl: "https://data.transportation.gov/api/views/kjg3-diqy/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 42,
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS AB Pass",
        taskId: "fmcsa-sms-ab-pass-daily",
        downloadUrl: "https://data.transportation.gov/api/views/m3ry-qcip/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 36,
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS C Pass",
        taskId: "fmcsa-sms-c-pass-daily",
        downloadUrl: "https://data.transportation.gov/api/views/h3zn-uid9/rows.csv?accessType=DOWNLOAD",
        expectedFieldCount: 36,
        sourceFileVariant: "csv_export",
      },
    ],
  );

  assert.deepEqual(FMCSA_SMS_FEED_CORRECTIONS.smsCPass, {
    originalCandidateDatasetId: "h9zy-gjn8",
    correctedDatasetId: "h3zn-uid9",
  });
  assert.deepEqual(FMCSA_SMS_SKIPPED_FEEDS, [
    {
      feedName: "SMS Input - Crash",
      candidateDatasetId: "gwak-5bwn",
      candidateDownloadUrl: "https://data.transportation.gov/download/gwak-5bwn/text%2Fplain",
      reason: "skipped_by_user_after_ambiguous_dataset_verification",
    },
  ]);
});

test("SMS workflow parses headered CSV exports and confirms persistence", async () => {
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
              feed_name: "SMS Input - Violation",
              feed_date: "2026-03-10",
              rows_received: 1,
              rows_written: 1,
            },
          },
        },
      ],
    }),
  });

  const result = await runFmcsaDailyDiffWorkflow(
    {
      feed: FMCSA_SMS_INPUT_VIOLATION_FEED,
      schedule: {
        timestamp: "2026-03-10T16:00:00.000Z",
        scheduleId: "schedule-sms-violations",
        timezone: "America/New_York",
      },
    },
    {
      client,
      fetchImpl: createDownloadFetch({
        contentType: "text/csv; charset=utf-8",
        text: [
          "Unique_ID,Insp_Date,DOT_Number,Viol_Code,BASIC_Desc,OOS_Indicator,OOS_Weight,Severity_Weight,Time_Weight,Total_Severity_Wght,Section_Desc,Group_Desc,Viol_Unit",
          '726403509,30-JAN-24,1926619,3922SLLS4,Unsafe Driving,false,0,10,1,10,"Failing to obey traffic control device","Traffic Control",D',
        ].join("\n"),
      }),
    },
  );

  assert.equal(result.feed_name, "SMS Input - Violation");
  assert.equal(result.source_file_variant, "csv_export");
  assert.equal(result.rows_downloaded, 1);
  assert.equal(result.rows_written, 1);

  const request = internalRequests[0];
  assert.equal(request?.path, "/api/internal/carrier-inspection-violations/upsert-batch");
  assert.equal(request?.body?.feed_name, "SMS Input - Violation");
  assert.equal(request?.body?.source_file_variant, "csv_export");
  assert.equal((request?.body?.records as unknown[])?.length, 1);
});

test("SMS workflow fails on header mismatch", async () => {
  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      { feed: FMCSA_SMS_INPUT_INSPECTION_FEED },
      {
        client: createUnusedClient(),
        fetchImpl: createDownloadFetch({
          contentType: "text/csv; charset=utf-8",
          text: [
            "wrong_header",
            "value",
          ].join("\n"),
        }),
      },
    ),
    /header validation failed/i,
  );
});

test("SMS workflow fails on invalid non-CSV content type", async () => {
  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      { feed: FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED },
      {
        client: createUnusedClient(),
        fetchImpl: (async () =>
          new Response("<html>not csv</html>", {
            status: 200,
            headers: { "Content-Type": "text/html; charset=utf-8" },
          })) as typeof fetch,
      },
    ),
    /unexpected content type|HTML instead of CSV/i,
  );
});

test("SMS pass and passproperty feeds remain distinct after candidate-id correction", () => {
  assert.equal(FMCSA_SMS_C_PASSPROPERTY_FEED.downloadUrl.includes("h9zy-gjn8"), true);
  assert.equal(FMCSA_SMS_C_PASS_FEED.downloadUrl.includes("h3zn-uid9"), true);
  assert.notEqual(FMCSA_SMS_C_PASSPROPERTY_FEED.expectedFieldCount, FMCSA_SMS_C_PASS_FEED.expectedFieldCount);
  assert.equal(FMCSA_SMS_AB_PASSPROPERTY_FEED.expectedFieldCount, 21);
  assert.equal(FMCSA_SMS_AB_PASS_FEED.expectedFieldCount, 36);
});

test("FMCSA daily diff feed_date follows the schedule timezone", () => {
  assert.equal(
    __testables.resolveFeedDate("2026-03-11T01:30:00.000Z", {
      timezone: "America/New_York",
    }),
    "2026-03-10",
  );
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

test("FMCSA daily and all-history parser enforces row width for representative next-batch feeds", () => {
  for (const feed of [
    FMCSA_CARRIER_DAILY_FEED,
    FMCSA_BOC3_DAILY_FEED,
    FMCSA_REJECTED_DAILY_FEED,
    FMCSA_AUTHHIST_ALL_HISTORY_FEED,
  ]) {
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
              feed_date: "2026-03-10",
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
