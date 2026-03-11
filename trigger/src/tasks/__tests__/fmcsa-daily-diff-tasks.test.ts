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
  FMCSA_CARRIER_ALL_HISTORY_CSV_FEED,
  FMCSA_CARRIER_DAILY_FEED,
  FMCSA_COMPANY_CENSUS_FILE_FEED,
  FMCSA_CRASH_FILE_FEED,
  FMCSA_INSHIST_DAILY_FEED,
  FMCSA_INSHIST_ALL_HISTORY_FEED,
  FMCSA_INSPECTIONS_AND_CITATIONS_FEED,
  FMCSA_INSPECTIONS_PER_UNIT_FEED,
  FMCSA_INSURANCE_DAILY_FEED,
  FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
  FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS,
  FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
  FMCSA_REJECTED_ALL_HISTORY_FEED,
  FMCSA_REJECTED_DAILY_FEED,
  FMCSA_REMAINING_CSV_EXPORT_FEEDS,
  FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED,
  FMCSA_REVOCATION_DAILY_FEED,
  FMCSA_SMS_AB_PASS_FEED,
  FMCSA_SMS_AB_PASSPROPERTY_FEED,
  FMCSA_SMS_C_PASS_FEED,
  FMCSA_SMS_C_PASSPROPERTY_FEED,
  FMCSA_SMS_FEEDS,
  FMCSA_SMS_INPUT_INSPECTION_FEED,
  FMCSA_SMS_INPUT_VIOLATION_FEED,
  FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED,
  FMCSA_TOP5_DAILY_DIFF_FEEDS,
  FMCSA_SPECIAL_STUDIES_FEED,
  FMCSA_VEHICLE_INSPECTION_FILE_FEED,
  FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED,
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

test("FMCSA SMS feed configs expose the expected feed-to-URL mapping", () => {
  assert.equal(FMCSA_SMS_FEEDS.length, 7);

  assert.deepEqual(
    FMCSA_SMS_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      taskId: feed.taskId,
      downloadUrl: feed.downloadUrl,
      sourceFileVariant: feed.sourceFileVariant,
    })),
    [
      {
        feedName: "SMS AB PassProperty",
        taskId: "fmcsa-sms-ab-passproperty-daily",
        downloadUrl: "https://data.transportation.gov/api/views/4y6x-dmck/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS C PassProperty",
        taskId: "fmcsa-sms-c-passproperty-daily",
        downloadUrl: "https://data.transportation.gov/api/views/h9zy-gjn8/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS Input - Violation",
        taskId: "fmcsa-sms-input-violation-daily",
        downloadUrl: "https://data.transportation.gov/api/views/8mt8-2mdr/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS Input - Inspection",
        taskId: "fmcsa-sms-input-inspection-daily",
        downloadUrl: "https://data.transportation.gov/api/views/rbkj-cgst/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS Input - Motor Carrier Census",
        taskId: "fmcsa-sms-motor-carrier-census-daily",
        downloadUrl: "https://data.transportation.gov/api/views/kjg3-diqy/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS AB Pass",
        taskId: "fmcsa-sms-ab-pass-daily",
        downloadUrl: "https://data.transportation.gov/api/views/m3ry-qcip/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "SMS C Pass",
        taskId: "fmcsa-sms-c-pass-daily",
        downloadUrl: "https://data.transportation.gov/api/views/h3zn-uid9/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
    ],
  );
});

test("FMCSA remaining CSV export feed configs expose the expected feed-to-URL mapping", () => {
  assert.equal(FMCSA_REMAINING_CSV_EXPORT_FEEDS.length, 11);

  assert.deepEqual(
    FMCSA_REMAINING_CSV_EXPORT_FEEDS.map((feed) => ({
      feedName: feed.feedName,
      taskId: feed.taskId,
      downloadUrl: feed.downloadUrl,
      sourceFileVariant: feed.sourceFileVariant,
    })),
    [
      {
        feedName: "Crash File",
        taskId: "fmcsa-crash-file-daily",
        downloadUrl: "https://data.transportation.gov/api/views/aayw-vxb3/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Carrier - All With History",
        taskId: "fmcsa-carrier-all-history-daily",
        downloadUrl: "https://data.transportation.gov/api/views/6eyk-hxee/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "Inspections Per Unit",
        taskId: "fmcsa-inspections-per-unit-daily",
        downloadUrl: "https://data.transportation.gov/api/views/wt8s-2hbx/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Special Studies",
        taskId: "fmcsa-special-studies-daily",
        downloadUrl: "https://data.transportation.gov/api/views/5qik-smay/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Revocation - All With History",
        taskId: "fmcsa-revocation-all-history-daily",
        downloadUrl: "https://data.transportation.gov/api/views/sa6p-acbp/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "Insur - All With History",
        taskId: "fmcsa-insur-all-history-daily",
        downloadUrl: "https://data.transportation.gov/api/views/ypjt-5ydn/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "all_with_history",
      },
      {
        feedName: "OUT OF SERVICE ORDERS",
        taskId: "fmcsa-out-of-service-orders-daily",
        downloadUrl: "https://data.transportation.gov/api/views/p2mt-9ige/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Inspections and Citations",
        taskId: "fmcsa-inspections-citations-daily",
        downloadUrl: "https://data.transportation.gov/api/views/qbt8-7vic/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Vehicle Inspections and Violations",
        taskId: "fmcsa-vehicle-inspections-violations-daily",
        downloadUrl: "https://data.transportation.gov/api/views/876r-jsdb/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Company Census File",
        taskId: "fmcsa-company-census-file-daily",
        downloadUrl: "https://data.transportation.gov/api/views/az4n-8mr2/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
      },
      {
        feedName: "Vehicle Inspection File",
        taskId: "fmcsa-vehicle-inspection-file-daily",
        downloadUrl: "https://data.transportation.gov/api/views/fx4q-ay7w/rows.csv?accessType=DOWNLOAD",
        sourceFileVariant: "csv_export",
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
    {
      filename: "../fmcsa-sms-ab-passproperty-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_AB_PASSPROPERTY_FEED.taskId",
      cronPattern: 'pattern: "36 11 * * *"',
    },
    {
      filename: "../fmcsa-sms-c-passproperty-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_C_PASSPROPERTY_FEED.taskId",
      cronPattern: 'pattern: "43 11 * * *"',
    },
    {
      filename: "../fmcsa-sms-input-violation-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_INPUT_VIOLATION_FEED.taskId",
      cronPattern: 'pattern: "50 11 * * *"',
    },
    {
      filename: "../fmcsa-sms-input-inspection-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_INPUT_INSPECTION_FEED.taskId",
      cronPattern: 'pattern: "57 11 * * *"',
    },
    {
      filename: "../fmcsa-sms-motor-carrier-census-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED.taskId",
      cronPattern: 'pattern: "4 12 * * *"',
    },
    {
      filename: "../fmcsa-sms-ab-pass-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_AB_PASS_FEED.taskId",
      cronPattern: 'pattern: "11 12 * * *"',
    },
    {
      filename: "../fmcsa-sms-c-pass-daily.ts",
      taskIdExpression: "id: FMCSA_SMS_C_PASS_FEED.taskId",
      cronPattern: 'pattern: "18 12 * * *"',
    },
    {
      filename: "../fmcsa-crash-file-daily.ts",
      taskIdExpression: "id: FMCSA_CRASH_FILE_FEED.taskId",
      cronPattern: 'pattern: "25 12 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-carrier-all-history-daily.ts",
      taskIdExpression: "id: FMCSA_CARRIER_ALL_HISTORY_CSV_FEED.taskId",
      cronPattern: 'pattern: "32 12 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-inspections-per-unit-daily.ts",
      taskIdExpression: "id: FMCSA_INSPECTIONS_PER_UNIT_FEED.taskId",
      cronPattern: 'pattern: "39 12 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-special-studies-daily.ts",
      taskIdExpression: "id: FMCSA_SPECIAL_STUDIES_FEED.taskId",
      cronPattern: 'pattern: "46 12 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-revocation-all-history-daily.ts",
      taskIdExpression: "id: FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED.taskId",
      cronPattern: 'pattern: "53 12 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-insur-all-history-daily.ts",
      taskIdExpression: "id: FMCSA_INSUR_ALL_HISTORY_CSV_FEED.taskId",
      cronPattern: 'pattern: "0 13 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-out-of-service-orders-daily.ts",
      taskIdExpression: "id: FMCSA_OUT_OF_SERVICE_ORDERS_FEED.taskId",
      cronPattern: 'pattern: "7 13 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 3600",
    },
    {
      filename: "../fmcsa-inspections-citations-daily.ts",
      taskIdExpression: "id: FMCSA_INSPECTIONS_AND_CITATIONS_FEED.taskId",
      cronPattern: 'pattern: "14 13 * * *"',
      machinePattern: 'machine: "small-2x"',
      maxDurationPattern: "maxDuration: 1800",
    },
    {
      filename: "../fmcsa-vehicle-inspections-violations-daily.ts",
      taskIdExpression: "id: FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED.taskId",
      cronPattern: 'pattern: "21 13 * * *"',
      machinePattern: 'machine: "small-2x"',
      maxDurationPattern: "maxDuration: 1800",
    },
    {
      filename: "../fmcsa-company-census-file-daily.ts",
      taskIdExpression: "id: FMCSA_COMPANY_CENSUS_FILE_FEED.taskId",
      cronPattern: 'pattern: "28 13 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 10800",
    },
    {
      filename: "../fmcsa-vehicle-inspection-file-daily.ts",
      taskIdExpression: "id: FMCSA_VEHICLE_INSPECTION_FILE_FEED.taskId",
      cronPattern: 'pattern: "35 13 * * *"',
      machinePattern: 'machine: "medium-2x"',
      maxDurationPattern: "maxDuration: 10800",
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
    if (taskExpectation.machinePattern != null) {
      const machinePattern = taskExpectation.machinePattern;
      assert.match(
        source,
        new RegExp(machinePattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      );
    }
    if (taskExpectation.maxDurationPattern != null) {
      const maxDurationPattern = taskExpectation.maxDurationPattern;
      assert.match(
        source,
        new RegExp(maxDurationPattern.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      );
    }
  }
});
