import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  FMCSA_ACTPENDINSUR_DAILY_FEED,
  FMCSA_AUTHHIST_DAILY_FEED,
  FMCSA_INSHIST_DAILY_FEED,
  FMCSA_INSURANCE_DAILY_FEED,
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

test("all five scheduled task files exist with daily staggered cron definitions", () => {
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
