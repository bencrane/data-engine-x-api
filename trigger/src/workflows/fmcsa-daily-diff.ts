import { logger } from "@trigger.dev/sdk/v3";
import { parse as parseCsv } from "csv-parse/sync";

import { createInternalApiClient, InternalApiClient } from "./internal-api.js";
import { writeDedicatedTableConfirmed } from "./persistence.js";

type FmcsaTop5FeedName =
  | "AuthHist"
  | "Revocation"
  | "Insurance"
  | "ActPendInsur"
  | "InsHist";

export interface FmcsaScheduledPayload {
  timestamp?: Date | string;
  lastTimestamp?: Date | string | null;
  timezone?: string | null;
  scheduleId?: string | null;
  externalId?: string | null;
  upcoming?: Array<Date | string> | null;
}

export interface FmcsaDailyDiffRow {
  row_number: number;
  raw_values: string[];
  raw_fields: Record<string, string>;
}

export interface FmcsaDailyDiffFeedConfig {
  feedName: FmcsaTop5FeedName;
  downloadUrl: string;
  taskId: string;
  internalUpsertPath: string;
  sourceFields: readonly string[];
  expectedFieldCount: number;
}

export interface FmcsaDailyDiffWorkflowPayload {
  feed: FmcsaDailyDiffFeedConfig;
  schedule?: FmcsaScheduledPayload;
  apiUrl?: string;
  internalApiKey?: string;
}

export interface FmcsaDailyDiffWorkflowDependencies {
  client?: InternalApiClient;
  fetchImpl?: typeof fetch;
}

export interface FmcsaDailyDiffWorkflowResult {
  feed_name: FmcsaTop5FeedName;
  download_url: string;
  observed_at: string;
  rows_downloaded: number;
  rows_parsed: number;
  rows_accepted: number;
  rows_rejected: number;
  rows_written: number;
}

interface FmcsaDailyDiffPersistenceResponse {
  feed_name: string;
  rows_received: number;
  rows_written: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function ensureStringArray(value: unknown, errorMessage: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(errorMessage);
  }

  return value.map((item) => (typeof item === "string" ? item : String(item ?? "")));
}

function normalizeTimestamp(value: Date | string | null | undefined): string | null {
  if (value instanceof Date) {
    return value.toISOString();
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  return null;
}

function normalizeObservedAt(schedule?: FmcsaScheduledPayload): string {
  return normalizeTimestamp(schedule?.timestamp) ?? new Date().toISOString();
}

function serializeSchedulePayload(
  schedule: FmcsaScheduledPayload | undefined,
  feed: FmcsaDailyDiffFeedConfig,
  observedAt: string,
): Record<string, unknown> {
  return {
    feed_name: feed.feedName,
    task_id: feed.taskId,
    observed_at: observedAt,
    schedule_timestamp: normalizeTimestamp(schedule?.timestamp),
    last_schedule_timestamp: normalizeTimestamp(schedule?.lastTimestamp),
    timezone: schedule?.timezone ?? null,
    schedule_id: schedule?.scheduleId ?? null,
    external_id: schedule?.externalId ?? null,
    upcoming: Array.isArray(schedule?.upcoming)
      ? schedule?.upcoming.map((value) => normalizeTimestamp(value) ?? String(value))
      : [],
  };
}

function parseDailyDiffBody(
  feed: FmcsaDailyDiffFeedConfig,
  rawBody: string,
): {
  rowsDownloaded: number;
  rowsParsed: number;
  rowsAccepted: number;
  rowsRejected: number;
  rows: FmcsaDailyDiffRow[];
} {
  if (rawBody.trim().length === 0) {
    throw new Error(`${feed.feedName} download returned an empty body`);
  }

  let parsedRecords: unknown;
  try {
    parsedRecords = parseCsv(rawBody, {
      bom: true,
      columns: false,
      skip_empty_lines: true,
      relax_column_count: true,
      trim: false,
    });
  } catch (error) {
    throw new Error(
      `${feed.feedName} CSV parsing failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  if (!Array.isArray(parsedRecords) || parsedRecords.length === 0) {
    throw new Error(`${feed.feedName} download contained no parseable rows`);
  }

  const rejectedRows: Array<{ rowNumber: number; width: number }> = [];
  const normalizedRows: FmcsaDailyDiffRow[] = [];

  parsedRecords.forEach((record, index) => {
    const rowNumber = index + 1;
    const values = ensureStringArray(record, `${feed.feedName} row ${rowNumber} is not a CSV value array`);

    if (values.length !== feed.expectedFieldCount) {
      rejectedRows.push({ rowNumber, width: values.length });
      return;
    }

    const rawFields: Record<string, string> = {};
    feed.sourceFields.forEach((fieldName, fieldIndex) => {
      rawFields[fieldName] = values[fieldIndex] ?? "";
    });

    normalizedRows.push({
      row_number: rowNumber,
      raw_values: values,
      raw_fields: rawFields,
    });
  });

  if (rejectedRows.length > 0) {
    const details = rejectedRows
      .slice(0, 10)
      .map((row) => `row ${row.rowNumber} width ${row.width}`)
      .join(", ");
    throw new Error(
      `${feed.feedName} row width validation failed: expected ${feed.expectedFieldCount} columns; ${details}`,
    );
  }

  return {
    rowsDownloaded: parsedRecords.length,
    rowsParsed: parsedRecords.length,
    rowsAccepted: normalizedRows.length,
    rowsRejected: rejectedRows.length,
    rows: normalizedRows,
  };
}

async function downloadDailyDiffText(
  fetchImpl: typeof fetch,
  feed: FmcsaDailyDiffFeedConfig,
): Promise<string> {
  let response: Response;
  try {
    response = await fetchImpl(feed.downloadUrl, {
      method: "GET",
      signal: AbortSignal.timeout(60_000),
    });
  } catch (error) {
    throw new Error(
      `${feed.feedName} download failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  if (!response.ok) {
    throw new Error(`${feed.feedName} download failed with HTTP ${response.status}`);
  }

  return response.text();
}

function createClient(
  payload: FmcsaDailyDiffWorkflowPayload,
  dependencies: FmcsaDailyDiffWorkflowDependencies,
): InternalApiClient {
  return (
    dependencies.client ??
    createInternalApiClient({
      authContext: {
        orgId: "system",
      },
      apiUrl: payload.apiUrl,
      internalApiKey: payload.internalApiKey,
    })
  );
}

async function persistDailyDiffRows(
  client: InternalApiClient,
  payload: FmcsaDailyDiffWorkflowPayload,
  rows: FmcsaDailyDiffRow[],
  observedAt: string,
): Promise<FmcsaDailyDiffPersistenceResponse> {
  const sourceRunMetadata = serializeSchedulePayload(payload.schedule, payload.feed, observedAt);

  return writeDedicatedTableConfirmed<FmcsaDailyDiffPersistenceResponse>(client, {
    path: payload.feed.internalUpsertPath,
    payload: {
      feed_name: payload.feed.feedName,
      download_url: payload.feed.downloadUrl,
      source_file_variant: "daily diff",
      source_observed_at: observedAt,
      source_task_id: payload.feed.taskId,
      source_schedule_id: payload.schedule?.scheduleId ?? null,
      source_run_metadata: sourceRunMetadata,
      records: rows,
    },
    validate: (response) =>
      isRecord(response) &&
      response.feed_name === payload.feed.feedName &&
      typeof response.rows_received === "number" &&
      typeof response.rows_written === "number" &&
      response.rows_received === rows.length &&
      response.rows_written >= 0,
    confirmationErrorMessage: `${payload.feed.feedName} persistence write could not be confirmed`,
  });
}

export async function runFmcsaDailyDiffWorkflow(
  payload: FmcsaDailyDiffWorkflowPayload,
  dependencies: FmcsaDailyDiffWorkflowDependencies = {},
): Promise<FmcsaDailyDiffWorkflowResult> {
  const client = createClient(payload, dependencies);
  const fetchImpl = dependencies.fetchImpl ?? fetch;
  const observedAt = normalizeObservedAt(payload.schedule);

  logger.info("fmcsa daily diff workflow start", {
    feed_name: payload.feed.feedName,
    download_url: payload.feed.downloadUrl,
    expected_field_count: payload.feed.expectedFieldCount,
    source_observed_at: observedAt,
    task_id: payload.feed.taskId,
    schedule_id: payload.schedule?.scheduleId ?? null,
  });

  const rawBody = await downloadDailyDiffText(fetchImpl, payload.feed);
  const parsed = parseDailyDiffBody(payload.feed, rawBody);
  const persistence = await persistDailyDiffRows(client, payload, parsed.rows, observedAt);

  const result: FmcsaDailyDiffWorkflowResult = {
    feed_name: payload.feed.feedName,
    download_url: payload.feed.downloadUrl,
    observed_at: observedAt,
    rows_downloaded: parsed.rowsDownloaded,
    rows_parsed: parsed.rowsParsed,
    rows_accepted: parsed.rowsAccepted,
    rows_rejected: parsed.rowsRejected,
    rows_written: persistence.rows_written,
  };

  logger.info("fmcsa daily diff workflow succeeded", result);
  return result;
}

export const FMCSA_AUTHHIST_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "AuthHist",
  downloadUrl: "https://data.transportation.gov/download/sn3k-dnx7/text%2Fplain",
  taskId: "fmcsa-authhist-daily",
  internalUpsertPath: "/api/internal/operating-authority-histories/upsert-batch",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "Sub Number",
    "Operating Authority Type",
    "Original Authority Action Description",
    "Original Authority Action Served Date",
    "Final Authority Action Description",
    "Final Authority Decision Date",
    "Final Authority Served Date",
  ],
  expectedFieldCount: 9,
};

export const FMCSA_REVOCATION_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Revocation",
  downloadUrl: "https://data.transportation.gov/download/pivg-szje/text%2Fplain",
  taskId: "fmcsa-revocation-daily",
  internalUpsertPath: "/api/internal/operating-authority-revocations/upsert-batch",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "Operating Authority Registration Type",
    "Serve Date",
    "Revocation Type",
    "Effective Date",
  ],
  expectedFieldCount: 6,
};

export const FMCSA_INSURANCE_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Insurance",
  downloadUrl: "https://data.transportation.gov/download/mzmm-6xep/text%2Fplain",
  taskId: "fmcsa-insurance-daily",
  internalUpsertPath: "/api/internal/insurance-policies/upsert-batch",
  sourceFields: [
    "Docket Number",
    "Insurance Type",
    "BI&PD Class",
    "BI&PD Maximum Dollar Limit",
    "BI&PD Underlying Dollar Limit",
    "Policy Number",
    "Effective Date",
    "Form Code",
    "Insurance Company Name",
  ],
  expectedFieldCount: 9,
};

export const FMCSA_ACTPENDINSUR_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "ActPendInsur",
  downloadUrl: "https://data.transportation.gov/download/chgs-tx6x/text%2Fplain",
  taskId: "fmcsa-actpendinsur-daily",
  internalUpsertPath: "/api/internal/insurance-policy-filings/upsert-batch",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "Form Code",
    "Insurance Type Description",
    "Insurance Company Name",
    "Policy Number",
    "Posted Date",
    "BI&PD Underlying Limit",
    "BI&PD Maximum Limit",
    "Effective Date",
    "Cancel Effective Date",
  ],
  expectedFieldCount: 11,
};

export const FMCSA_INSHIST_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "InsHist",
  downloadUrl: "https://data.transportation.gov/download/xkmg-ff2t/text%2Fplain",
  taskId: "fmcsa-inshist-daily",
  internalUpsertPath: "/api/internal/insurance-policy-history-events/upsert-batch",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "Form Code",
    "Cancellation Method",
    "Cancel/Replace/Name Change/Transfer Form",
    "Insurance Type Indicator",
    "Insurance Type Description",
    "Policy Number",
    "Minimum Coverage Amount",
    "Insurance Class Code",
    "Effective Date",
    "BI&PD Underlying Limit Amount",
    "BI&PD Max Coverage Amount",
    "Cancel Effective Date",
    "Specific Cancellation Method",
    "Insurance Company Branch",
    "Insurance Company Name",
  ],
  expectedFieldCount: 17,
};

export const FMCSA_TOP5_DAILY_DIFF_FEEDS = [
  FMCSA_AUTHHIST_DAILY_FEED,
  FMCSA_REVOCATION_DAILY_FEED,
  FMCSA_INSURANCE_DAILY_FEED,
  FMCSA_ACTPENDINSUR_DAILY_FEED,
  FMCSA_INSHIST_DAILY_FEED,
] as const;

export const __testables = {
  parseDailyDiffBody,
  serializeSchedulePayload,
};
