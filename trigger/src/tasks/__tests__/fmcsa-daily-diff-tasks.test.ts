import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED,
  FMCSA_ACTPENDINSUR_DAILY_FEED,
  FMCSA_AUTHHIST_ALL_HISTORY_FEED,
  FMCSA_AUTHHIST_DAILY_FEED,
  FMCSA_BOC3_ALL_HISTORY_FEED,
  FMCSA_BOC3_DAILY_FEED,
  FMCSA_CARRIER_DAILY_FEED,
  FMCSA_INSHIST_DAILY_FEED,
  FMCSA_INSHIST_ALL_HISTORY_FEED,
  FMCSA_INSURANCE_DAILY_FEED,
  FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS,
  FMCSA_REJECTED_ALL_HISTORY_FEED,
  FMCSA_REJECTED_DAILY_FEED,
  FMCSA_REVOCATION_DAILY_FEED,
  FMCSA_TOP5_DAILY_DIFF_FEEDS,
} from "../../workflows/fmcsa-daily-diff.js";

test("FMCSA top-5 feed configs expose the expected feed-to-URL mapping", () => {
  assert.equal(FMCSA_TOP5_DAILY_DIFF_FEEDS.length, 5);

  assert.deepEqual(
    FMCSA_TOP5_DAILY_DIFF_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      taskId: feed.taskId,
      downloadUrl: feed.downloadUrl,
    })),
    [
      {
        feedName: "AuthHist",
        taskId: "fmcsa-authhist-daily",
        downloadUrl: "https://data.transportation.gov/download/sn3k-dnx7/text%2Fplain",
      },
      {
        feedName: "Revocation",
        taskId: "fmcsa-revocation-daily",
        downloadUrl: "https://data.transportation.gov/download/pivg-szje/text%2Fplain",
      },
      {
        feedName: "Insurance",
        taskId: "fmcsa-insurance-daily",
        downloadUrl: "https://data.transportation.gov/download/mzmm-6xep/text%2Fplain",
      },
      {
        feedName: "ActPendInsur",
        taskId: "fmcsa-actpendinsur-daily",
        downloadUrl: "https://data.transportation.gov/download/chgs-tx6x/text%2Fplain",
      },
      {
        feedName: "InsHist",
        taskId: "fmcsa-inshist-daily",
        downloadUrl: "https://data.transportation.gov/download/xkmg-ff2t/text%2Fplain",
      },
    ],
  );
});

test("FMCSA next-batch feed configs expose the expected feed-to-URL mapping", () => {
  assert.equal(FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS.length, 8);

  assert.deepEqual(
    FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      taskId: feed.taskId,
      downloadUrl: feed.downloadUrl,
      sourceFileVariant: feed.sourceFileVariant,
    })),
    [
      {
        feedName: "Carrier",
        taskId: "fmcsa-carrier-daily",
        downloadUrl: "https://data.transportation.gov/download/6qg9-x4f8/text%2Fplain",
        sourceFileVariant: "daily",
      },
      {
        feedName: "Rejected",
        taskId: "fmcsa-rejected-daily",
        downloadUrl: "https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain",
        sourceFileVariant: "daily",
      },
      {
        feedName: "BOC3",
        taskId: "fmcsa-boc3-daily",
        downloadUrl: "https://data.transportation.gov/download/fb8g-ngam/text%2Fplain",
        sourceFileVariant: "daily",
      },
      {
        feedName: "InsHist - All With History",
        taskId: "fmcsa-inshist-all-history",
        downloadUrl: "https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "BOC3 - All With History",
        taskId: "fmcsa-boc3-all-history",
        downloadUrl: "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "ActPendInsur - All With History",
        taskId: "fmcsa-actpendinsur-all-history",
        downloadUrl: "https://data.transportation.gov/download/y77m-3nfx/text%2Fplain",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "Rejected - All With History",
        taskId: "fmcsa-rejected-all-history",
        downloadUrl: "https://data.transportation.gov/download/9m5y-imtw/text%2Fplain",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "AuthHist - All With History",
        taskId: "fmcsa-authhist-all-history",
        downloadUrl: "https://data.transportation.gov/download/wahn-z3rq/text%2Fplain",
        sourceFileVariant: "all_with_history",
      },
    ],
  );
});

test("all FMCSA scheduled task files exist with staggered cron definitions", () => {
  const taskExpectations = [
    {
      filename: "../fmcsa-authhist-daily.ts",
      taskIdExpression: "id: FMCSA_AUTHHIST_DAILY_FEED.taskId",
      cronPattern: 'pattern: "5 10 * * *"',
    },
    {
      filename: "../fmcsa-revocation-daily.ts",
      taskIdExpression: "id: FMCSA_REVOCATION_DAILY_FEED.taskId",
      cronPattern: 'pattern: "12 10 * * *"',
    },
    {
      filename: "../fmcsa-insurance-daily.ts",
      taskIdExpression: "id: FMCSA_INSURANCE_DAILY_FEED.taskId",
      cronPattern: 'pattern: "19 10 * * *"',
    },
    {
      filename: "../fmcsa-actpendinsur-daily.ts",
      taskIdExpression: "id: FMCSA_ACTPENDINSUR_DAILY_FEED.taskId",
      cronPattern: 'pattern: "26 10 * * *"',
    },
    {
      filename: "../fmcsa-inshist-daily.ts",
      taskIdExpression: "id: FMCSA_INSHIST_DAILY_FEED.taskId",
      cronPattern: 'pattern: "33 10 * * *"',
    },
    {
      filename: "../fmcsa-carrier-daily.ts",
      taskIdExpression: "id: FMCSA_CARRIER_DAILY_FEED.taskId",
      cronPattern: 'pattern: "40 10 * * *"',
    },
    {
      filename: "../fmcsa-rejected-daily.ts",
      taskIdExpression: "id: FMCSA_REJECTED_DAILY_FEED.taskId",
      cronPattern: 'pattern: "47 10 * * *"',
    },
    {
      filename: "../fmcsa-boc3-daily.ts",
      taskIdExpression: "id: FMCSA_BOC3_DAILY_FEED.taskId",
      cronPattern: 'pattern: "54 10 * * *"',
    },
    {
      filename: "../fmcsa-inshist-all-history.ts",
      taskIdExpression: "id: FMCSA_INSHIST_ALL_HISTORY_FEED.taskId",
      cronPattern: 'pattern: "1 11 * * *"',
    },
    {
      filename: "../fmcsa-boc3-all-history.ts",
      taskIdExpression: "id: FMCSA_BOC3_ALL_HISTORY_FEED.taskId",
      cronPattern: 'pattern: "8 11 * * *"',
    },
    {
      filename: "../fmcsa-actpendinsur-all-history.ts",
      taskIdExpression: "id: FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED.taskId",
      cronPattern: 'pattern: "15 11 * * *"',
    },
    {
      filename: "../fmcsa-rejected-all-history.ts",
      taskIdExpression: "id: FMCSA_REJECTED_ALL_HISTORY_FEED.taskId",
      cronPattern: 'pattern: "22 11 * * *"',
    },
    {
      filename: "../fmcsa-authhist-all-history.ts",
      taskIdExpression: "id: FMCSA_AUTHHIST_ALL_HISTORY_FEED.taskId",
      cronPattern: 'pattern: "29 11 * * *"',
    },
  ];

  for (const taskExpectation of taskExpectations) {
    const filePath = resolve(process.cwd(), "src", "tasks", taskExpectation.filename.replace("../", ""));
    const source = readFileSync(filePath, "utf8");

    assert.match(source, /schedules\.task\(/);
    assert.match(
      source,
      new RegExp(taskExpectation.taskIdExpression.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    );
    assert.match(source, /timezone: "America\/New_York"/);
    assert.match(source, new RegExp(taskExpectation.cronPattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
});
