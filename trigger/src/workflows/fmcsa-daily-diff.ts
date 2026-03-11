import { logger } from "@trigger.dev/sdk/v3";
import { parse as parseCsv } from "csv-parse/sync";

import { createInternalApiClient, InternalApiClient } from "./internal-api.js";
import { writeDedicatedTableConfirmed } from "./persistence.js";

type FmcsaFeedName =
  | "AuthHist"
  | "Revocation"
  | "Insurance"
  | "ActPendInsur"
  | "InsHist"
  | "Carrier"
  | "Rejected"
  | "BOC3"
  | "InsHist - All With History"
  | "BOC3 - All With History"
  | "ActPendInsur - All With History"
  | "Rejected - All With History"
  | "AuthHist - All With History"
  | "SMS AB PassProperty"
  | "SMS C PassProperty"
  | "SMS Input - Violation"
  | "SMS Input - Inspection"
  | "SMS Input - Motor Carrier Census"
  | "SMS AB Pass"
  | "SMS C Pass";

export type FmcsaSourceFileVariant = "daily diff" | "daily" | "all_with_history" | "csv_export";

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
  feedName: FmcsaFeedName;
  downloadUrl: string;
  taskId: string;
  internalUpsertPath: string;
  sourceFileVariant: FmcsaSourceFileVariant;
  sourceFields: readonly string[];
  expectedFieldCount: number;
  headerRow?: readonly string[];
  expectedContentTypes?: readonly string[];
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
  feed_name: FmcsaFeedName;
  feed_date: string;
  download_url: string;
  source_file_variant: FmcsaSourceFileVariant;
  observed_at: string;
  rows_downloaded: number;
  rows_parsed: number;
  rows_accepted: number;
  rows_rejected: number;
  rows_written: number;
}

interface FmcsaDailyDiffPersistenceResponse {
  feed_name: string;
  feed_date: string;
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

function resolveFeedDate(
  observedAt: string,
  schedule?: FmcsaScheduledPayload,
): string {
  const date = new Date(observedAt);
  const timezone = schedule?.timezone ?? "UTC";

  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  const parts = formatter.formatToParts(date);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;

  if (!year || !month || !day) {
    throw new Error(`Unable to resolve feed_date for ${observedAt}`);
  }

  return `${year}-${month}-${day}`;
}

function serializeSchedulePayload(
  schedule: FmcsaScheduledPayload | undefined,
  feed: FmcsaDailyDiffFeedConfig,
  feedDate: string,
  observedAt: string,
): Record<string, unknown> {
  return {
    feed_name: feed.feedName,
    feed_date: feedDate,
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
  if (rawBody.trimStart().toLowerCase().startsWith("<!doctype html") || rawBody.includes("<html")) {
    throw new Error(`${feed.feedName} download returned HTML instead of CSV data`);
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

  let dataRecords = parsedRecords;
  if (feed.headerRow) {
    const headerRow = ensureStringArray(
      parsedRecords[0],
      `${feed.feedName} header row is not a CSV value array`,
    );

    if (headerRow.length !== feed.headerRow.length) {
      throw new Error(
        `${feed.feedName} header row width validation failed: expected ${feed.headerRow.length} columns but received ${headerRow.length}`,
      );
    }

    const mismatchedHeaderIndex = feed.headerRow.findIndex(
      (expectedHeader, index) => headerRow[index] !== expectedHeader,
    );
    if (mismatchedHeaderIndex >= 0) {
      throw new Error(
        `${feed.feedName} header validation failed at column ${mismatchedHeaderIndex + 1}: expected "${feed.headerRow[mismatchedHeaderIndex]}" but received "${headerRow[mismatchedHeaderIndex]}"`,
      );
    }

    dataRecords = parsedRecords.slice(1);
    if (dataRecords.length === 0) {
      throw new Error(`${feed.feedName} download contained a header row but no data rows`);
    }
  }

  const rejectedRows: Array<{ rowNumber: number; width: number }> = [];
  const normalizedRows: FmcsaDailyDiffRow[] = [];

  dataRecords.forEach((record, index) => {
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
    rowsDownloaded: dataRecords.length,
    rowsParsed: dataRecords.length,
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

  const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";
  if (feed.expectedContentTypes && !feed.expectedContentTypes.some((value) => contentType.includes(value))) {
    throw new Error(
      `${feed.feedName} download returned unexpected content type "${response.headers.get("Content-Type") ?? "unknown"}"`,
    );
  }
  if (contentType.includes("text/html")) {
    throw new Error(`${feed.feedName} download returned HTML instead of CSV data`);
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
  feedDate: string,
  observedAt: string,
): Promise<FmcsaDailyDiffPersistenceResponse> {
  const sourceRunMetadata = serializeSchedulePayload(payload.schedule, payload.feed, feedDate, observedAt);

  return writeDedicatedTableConfirmed<FmcsaDailyDiffPersistenceResponse>(client, {
    path: payload.feed.internalUpsertPath,
    payload: {
      feed_name: payload.feed.feedName,
      feed_date: feedDate,
      download_url: payload.feed.downloadUrl,
      source_file_variant: payload.feed.sourceFileVariant,
      source_observed_at: observedAt,
      source_task_id: payload.feed.taskId,
      source_schedule_id: payload.schedule?.scheduleId ?? null,
      source_run_metadata: sourceRunMetadata,
      records: rows,
    },
    validate: (response) =>
      isRecord(response) &&
      response.feed_name === payload.feed.feedName &&
      response.feed_date === feedDate &&
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
  const feedDate = resolveFeedDate(observedAt, payload.schedule);

  logger.info("fmcsa snapshot workflow start", {
    feed_name: payload.feed.feedName,
    feed_date: feedDate,
    download_url: payload.feed.downloadUrl,
    source_file_variant: payload.feed.sourceFileVariant,
    expected_field_count: payload.feed.expectedFieldCount,
    source_observed_at: observedAt,
    task_id: payload.feed.taskId,
    schedule_id: payload.schedule?.scheduleId ?? null,
  });

  const rawBody = await downloadDailyDiffText(fetchImpl, payload.feed);
  const parsed = parseDailyDiffBody(payload.feed, rawBody);
  const persistence = await persistDailyDiffRows(client, payload, parsed.rows, feedDate, observedAt);

  const result: FmcsaDailyDiffWorkflowResult = {
    feed_name: payload.feed.feedName,
    feed_date: feedDate,
    download_url: payload.feed.downloadUrl,
    source_file_variant: payload.feed.sourceFileVariant,
    observed_at: observedAt,
    rows_downloaded: parsed.rowsDownloaded,
    rows_parsed: parsed.rowsParsed,
    rows_accepted: parsed.rowsAccepted,
    rows_rejected: parsed.rowsRejected,
    rows_written: persistence.rows_written,
  };

  logger.info("fmcsa snapshot workflow succeeded", { ...result });
  return result;
}

export const FMCSA_AUTHHIST_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "AuthHist",
  downloadUrl: "https://data.transportation.gov/download/sn3k-dnx7/text%2Fplain",
  taskId: "fmcsa-authhist-daily",
  internalUpsertPath: "/api/internal/operating-authority-histories/upsert-batch",
  sourceFileVariant: "daily diff",
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
  sourceFileVariant: "daily diff",
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
  sourceFileVariant: "daily diff",
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
  sourceFileVariant: "daily diff",
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
  sourceFileVariant: "daily diff",
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

export const FMCSA_CARRIER_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Carrier",
  downloadUrl: "https://data.transportation.gov/download/6qg9-x4f8/text%2Fplain",
  taskId: "fmcsa-carrier-daily",
  internalUpsertPath: "/api/internal/carrier-registrations/upsert-batch",
  sourceFileVariant: "daily",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "MX Type",
    "RFC Number",
    "Common Authority",
    "Contract Authority",
    "Broker Authority",
    "Pending Common Authority",
    "Pending Contract Authority",
    "Pending Broker Authority",
    "Common Authority Revocation",
    "Contract Authority Revocation",
    "Broker Authority Revocation",
    "Property",
    "Passenger",
    "Household Goods",
    "Private Check",
    "Enterprise Check",
    "BIPD Required",
    "Cargo Required",
    "Bond/Surety Required",
    "BIPD on File",
    "Cargo on File",
    "Bond/Surety on File",
    "Address Status",
    "DBA Name",
    "Legal Name",
    "Business Address - PO Box/Street",
    "Business Address - Colonia",
    "Business Address - City",
    "Business Address - State Code",
    "Business Address - Country Code",
    "Business Address - Zip Code",
    "Business Address - Telephone Number",
    "Business Address - Fax Number",
    "Mailing Address - PO Box/Street",
    "Mailing Address - Colonia",
    "Mailing Address - City",
    "Mailing Address - State Code",
    "Mailing Address - Country Code",
    "Mailing Address - Zip Code",
    "Mailing Address - Telephone Number",
    "Mailing Address - Fax Number",
  ],
  expectedFieldCount: 43,
};

export const FMCSA_REJECTED_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Rejected",
  downloadUrl: "https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain",
  taskId: "fmcsa-rejected-daily",
  internalUpsertPath: "/api/internal/insurance-filing-rejections/upsert-batch",
  sourceFileVariant: "daily",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "Form Code (Insurance or Cancel)",
    "Insurance Type Description",
    "Policy Number",
    "Received Date",
    "Insurance Class Code",
    "Insurance Type Code",
    "Underlying Limit Amount",
    "Maximum Coverage Amount",
    "Rejected Date",
    "Insurance Branch",
    "Company Name",
    "Rejected Reason",
    "Minimum Coverage Amount",
  ],
  expectedFieldCount: 15,
};

export const FMCSA_BOC3_DAILY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "BOC3",
  downloadUrl: "https://data.transportation.gov/download/fb8g-ngam/text%2Fplain",
  taskId: "fmcsa-boc3-daily",
  internalUpsertPath: "/api/internal/process-agent-filings/upsert-batch",
  sourceFileVariant: "daily",
  sourceFields: [
    "Docket Number",
    "USDOT Number",
    "Company Name",
    "Attention to or Title",
    "Street or PO Box",
    "City",
    "State",
    "Country",
    "Zip Code",
  ],
  expectedFieldCount: 9,
};

export const FMCSA_INSHIST_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "InsHist - All With History",
  downloadUrl: "https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain",
  taskId: "fmcsa-inshist-all-history",
  internalUpsertPath: "/api/internal/insurance-policy-history-events/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_INSHIST_DAILY_FEED.sourceFields],
  expectedFieldCount: 17,
};

export const FMCSA_BOC3_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "BOC3 - All With History",
  downloadUrl: "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain",
  taskId: "fmcsa-boc3-all-history",
  internalUpsertPath: "/api/internal/process-agent-filings/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_BOC3_DAILY_FEED.sourceFields],
  expectedFieldCount: 9,
};

export const FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "ActPendInsur - All With History",
  downloadUrl: "https://data.transportation.gov/download/y77m-3nfx/text%2Fplain",
  taskId: "fmcsa-actpendinsur-all-history",
  internalUpsertPath: "/api/internal/insurance-policy-filings/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_ACTPENDINSUR_DAILY_FEED.sourceFields],
  expectedFieldCount: 11,
};

export const FMCSA_REJECTED_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Rejected - All With History",
  downloadUrl: "https://data.transportation.gov/download/9m5y-imtw/text%2Fplain",
  taskId: "fmcsa-rejected-all-history",
  internalUpsertPath: "/api/internal/insurance-filing-rejections/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_REJECTED_DAILY_FEED.sourceFields],
  expectedFieldCount: 15,
};

export const FMCSA_AUTHHIST_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "AuthHist - All With History",
  downloadUrl: "https://data.transportation.gov/download/wahn-z3rq/text%2Fplain",
  taskId: "fmcsa-authhist-all-history",
  internalUpsertPath: "/api/internal/operating-authority-histories/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_AUTHHIST_DAILY_FEED.sourceFields],
  expectedFieldCount: 9,
};

export const FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_FEEDS = [
  FMCSA_CARRIER_DAILY_FEED,
  FMCSA_REJECTED_DAILY_FEED,
  FMCSA_BOC3_DAILY_FEED,
  FMCSA_INSHIST_ALL_HISTORY_FEED,
  FMCSA_BOC3_ALL_HISTORY_FEED,
  FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED,
  FMCSA_REJECTED_ALL_HISTORY_FEED,
  FMCSA_AUTHHIST_ALL_HISTORY_FEED,
] as const;

const SMS_PASSPROPERTY_SOURCE_FIELDS = [
  "DOT_NUMBER",
  "INSP_TOTAL",
  "DRIVER_INSP_TOTAL",
  "DRIVER_OOS_INSP_TOTAL",
  "VEHICLE_INSP_TOTAL",
  "VEHICLE_OOS_INSP_TOTAL",
  "UNSAFE_DRIV_INSP_W_VIOL",
  "UNSAFE_DRIV_MEASURE",
  "UNSAFE_DRIV_AC",
  "HOS_DRIV_INSP_W_VIOL",
  "HOS_DRIV_MEASURE",
  "HOS_DRIV_AC",
  "DRIV_FIT_INSP_W_VIOL",
  "DRIV_FIT_MEASURE",
  "DRIV_FIT_AC",
  "CONTR_SUBST_INSP_W_VIOL",
  "CONTR_SUBST_MEASURE",
  "CONTR_SUBST_AC",
  "VEH_MAINT_INSP_W_VIOL",
  "VEH_MAINT_MEASURE",
  "VEH_MAINT_AC",
] as const;

const SMS_PASS_SOURCE_FIELDS = [
  "DOT_NUMBER",
  "INSP_TOTAL",
  "DRIVER_INSP_TOTAL",
  "DRIVER_OOS_INSP_TOTAL",
  "VEHICLE_INSP_TOTAL",
  "VEHICLE_OOS_INSP_TOTAL",
  "UNSAFE_DRIV_INSP_W_VIOL",
  "UNSAFE_DRIV_MEASURE",
  "UNSAFE_DRIV_PCT",
  "UNSAFE_DRIV_RD_ALERT",
  "UNSAFE_DRIV_AC",
  "UNSAFE_DRIV_BASIC_ALERT",
  "HOS_DRIV_INSP_W_VIOL",
  "HOS_DRIV_MEASURE",
  "HOS_DRIV_PCT",
  "HOS_DRIV_RD_ALERT",
  "HOS_DRIV_AC",
  "HOS_DRIV_BASIC_ALERT",
  "DRIV_FIT_INSP_W_VIOL",
  "DRIV_FIT_MEASURE",
  "DRIV_FIT_PCT",
  "DRIV_FIT_RD_ALERT",
  "DRIV_FIT_AC",
  "DRIV_FIT_BASIC_ALERT",
  "CONTR_SUBST_INSP_W_VIOL",
  "CONTR_SUBST_MEASURE",
  "CONTR_SUBST_PCT",
  "CONTR_SUBST_RD_ALERT",
  "CONTR_SUBST_AC",
  "CONTR_SUBST_BASIC_ALERT",
  "VEH_MAINT_INSP_W_VIOL",
  "VEH_MAINT_MEASURE",
  "VEH_MAINT_PCT",
  "VEH_MAINT_RD_ALERT",
  "VEH_MAINT_AC",
  "VEH_MAINT_BASIC_ALERT",
] as const;

const SMS_INPUT_VIOLATION_SOURCE_FIELDS = [
  "Unique_ID",
  "Insp_Date",
  "DOT_Number",
  "Viol_Code",
  "BASIC_Desc",
  "OOS_Indicator",
  "OOS_Weight",
  "Severity_Weight",
  "Time_Weight",
  "Total_Severity_Wght",
  "Section_Desc",
  "Group_Desc",
  "Viol_Unit",
] as const;

const SMS_INPUT_INSPECTION_SOURCE_FIELDS = [
  "Unique_ID",
  "Report_Number",
  "Report_State",
  "DOT_Number",
  "Insp_Date",
  "Insp_level_ID",
  "County_code_State",
  "Time_Weight",
  "Driver_OOS_Total",
  "Vehicle_OOS_Total",
  "Total_Hazmat_Sent",
  "OOS_Total",
  "Hazmat_OOS_Total",
  "Hazmat_Placard_req",
  "Unit_Type_Desc",
  "Unit_Make",
  "Unit_License",
  "Unit_License_State",
  "VIN",
  "Unit_Decal_Number",
  "Unit_Type_Desc2",
  "Unit_Make2",
  "Unit_License2",
  "Unit_License_State2",
  "VIN2",
  "Unit_Decal_Number2",
  "Unsafe_Insp",
  "Fatigued_Insp",
  "Dr_Fitness_Insp",
  "Subt_Alcohol_Insp",
  "Vh_Maint_Insp",
  "HM_Insp",
  "BASIC_Viol",
  "Unsafe_Viol",
  "Fatigued_Viol",
  "Dr_Fitness_Viol",
  "Subt_Alcohol_Viol",
  "Vh_Maint_Viol",
  "HM_Viol",
] as const;

const SMS_MOTOR_CARRIER_CENSUS_SOURCE_FIELDS = [
  "DOT_NUMBER",
  "LEGAL_NAME",
  "DBA_NAME",
  "CARRIER_OPERATION",
  "HM_FLAG",
  "PC_FLAG",
  "PHY_STREET",
  "PHY_CITY",
  "PHY_STATE",
  "PHY_ZIP",
  "PHY_COUNTRY",
  "MAILING_STREET",
  "MAILING_CITY",
  "MAILING_STATE",
  "MAILING_ZIP",
  "MAILING_COUNTRY",
  "TELEPHONE",
  "FAX",
  "EMAIL_ADDRESS",
  "MCS150_DATE",
  "MCS150_MILEAGE",
  "MCS150_MILEAGE_YEAR",
  "ADD_DATE",
  "OIC_STATE",
  "NBR_POWER_UNIT",
  "DRIVER_TOTAL",
  "RECENT_MILEAGE",
  "RECENT_MILEAGE_YEAR",
  "VMT_SOURCE_ID",
  "PRIVATE_ONLY",
  "AUTHORIZED_FOR_HIRE",
  "EXEMPT_FOR_HIRE",
  "PRIVATE_PROPERTY",
  "PRIVATE_PASSENGER_BUSINESS",
  "PRIVATE_PASSENGER_NONBUSINESS",
  "MIGRANT",
  "US_MAIL",
  "FEDERAL_GOVERNMENT",
  "STATE_GOVERNMENT",
  "LOCAL_GOVERNMENT",
  "INDIAN_TRIBE",
  "OP_OTHER",
] as const;

export const FMCSA_SMS_AB_PASSPROPERTY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS AB PassProperty",
  downloadUrl: "https://data.transportation.gov/api/views/4y6x-dmck/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-ab-passproperty-daily",
  internalUpsertPath: "/api/internal/carrier-safety-basic-measures/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_PASSPROPERTY_SOURCE_FIELDS,
  expectedFieldCount: SMS_PASSPROPERTY_SOURCE_FIELDS.length,
  headerRow: SMS_PASSPROPERTY_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_C_PASSPROPERTY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS C PassProperty",
  downloadUrl: "https://data.transportation.gov/api/views/h9zy-gjn8/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-c-passproperty-daily",
  internalUpsertPath: "/api/internal/carrier-safety-basic-measures/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_PASSPROPERTY_SOURCE_FIELDS,
  expectedFieldCount: SMS_PASSPROPERTY_SOURCE_FIELDS.length,
  headerRow: SMS_PASSPROPERTY_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_INPUT_VIOLATION_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS Input - Violation",
  downloadUrl: "https://data.transportation.gov/api/views/8mt8-2mdr/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-input-violation-daily",
  internalUpsertPath: "/api/internal/carrier-inspection-violations/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_INPUT_VIOLATION_SOURCE_FIELDS,
  expectedFieldCount: SMS_INPUT_VIOLATION_SOURCE_FIELDS.length,
  headerRow: SMS_INPUT_VIOLATION_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_INPUT_INSPECTION_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS Input - Inspection",
  downloadUrl: "https://data.transportation.gov/api/views/rbkj-cgst/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-input-inspection-daily",
  internalUpsertPath: "/api/internal/carrier-inspections/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_INPUT_INSPECTION_SOURCE_FIELDS,
  expectedFieldCount: SMS_INPUT_INSPECTION_SOURCE_FIELDS.length,
  headerRow: SMS_INPUT_INSPECTION_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS Input - Motor Carrier Census",
  downloadUrl: "https://data.transportation.gov/api/views/kjg3-diqy/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-motor-carrier-census-daily",
  internalUpsertPath: "/api/internal/motor-carrier-census-records/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_MOTOR_CARRIER_CENSUS_SOURCE_FIELDS,
  expectedFieldCount: SMS_MOTOR_CARRIER_CENSUS_SOURCE_FIELDS.length,
  headerRow: SMS_MOTOR_CARRIER_CENSUS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_AB_PASS_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS AB Pass",
  downloadUrl: "https://data.transportation.gov/api/views/m3ry-qcip/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-ab-pass-daily",
  internalUpsertPath: "/api/internal/carrier-safety-basic-percentiles/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_PASS_SOURCE_FIELDS,
  expectedFieldCount: SMS_PASS_SOURCE_FIELDS.length,
  headerRow: SMS_PASS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_C_PASS_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "SMS C Pass",
  downloadUrl: "https://data.transportation.gov/api/views/h3zn-uid9/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-sms-c-pass-daily",
  internalUpsertPath: "/api/internal/carrier-safety-basic-percentiles/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: SMS_PASS_SOURCE_FIELDS,
  expectedFieldCount: SMS_PASS_SOURCE_FIELDS.length,
  headerRow: SMS_PASS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_SMS_FEEDS = [
  FMCSA_SMS_AB_PASSPROPERTY_FEED,
  FMCSA_SMS_C_PASSPROPERTY_FEED,
  FMCSA_SMS_INPUT_VIOLATION_FEED,
  FMCSA_SMS_INPUT_INSPECTION_FEED,
  FMCSA_SMS_MOTOR_CARRIER_CENSUS_FEED,
  FMCSA_SMS_AB_PASS_FEED,
  FMCSA_SMS_C_PASS_FEED,
] as const;

export const FMCSA_SMS_SKIPPED_FEEDS = [
  {
    feedName: "SMS Input - Crash",
    candidateDatasetId: "gwak-5bwn",
    candidateDownloadUrl: "https://data.transportation.gov/download/gwak-5bwn/text%2Fplain",
    reason: "skipped_by_user_after_ambiguous_dataset_verification",
  },
] as const;

export const FMCSA_SMS_FEED_CORRECTIONS = {
  smsCPass: {
    originalCandidateDatasetId: "h9zy-gjn8",
    correctedDatasetId: "h3zn-uid9",
  },
} as const;

export const __testables = {
  parseDailyDiffBody,
  resolveFeedDate,
  serializeSchedulePayload,
};
