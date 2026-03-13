import { logger } from "@trigger.dev/sdk/v3";
import { createHash } from "node:crypto";
import { createReadStream, createWriteStream, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pipeline } from "node:stream/promises";
import { Readable } from "node:stream";
import { createGzip, gzipSync } from "node:zlib";
import { createClient as createSupabaseClient } from "@supabase/supabase-js";
import { parse as createCsvStreamParser } from "csv-parse";
import { parse as parseCsvSync } from "csv-parse/sync";
import { Upload as TusUpload } from "tus-js-client";

import {
  createInternalApiClient,
  InternalApiClient,
  InternalApiError,
  InternalApiTimeoutError,
} from "./internal-api.js";
import {
  PersistenceConfirmationError,
  writeDedicatedTableConfirmed,
} from "./persistence.js";

export const FMCSA_ARTIFACTS_BUCKET = "fmcsa-artifacts";

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
  | "SMS C Pass"
  | "Crash File"
  | "Carrier - All With History"
  | "Inspections Per Unit"
  | "Special Studies"
  | "Revocation - All With History"
  | "Insur - All With History"
  | "OUT OF SERVICE ORDERS"
  | "Inspections and Citations"
  | "Vehicle Inspections and Violations"
  | "Company Census File"
  | "Vehicle Inspection File";

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
  useStreamingParser?: boolean;
  writeBatchSize?: number;
  downloadTimeoutMs?: number;
  persistenceTimeoutMs?: number;
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
  supabaseClient?: SupabaseStorageClient;
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

interface FmcsaArtifactIngestManifest {
  feed_name: string;
  feed_date: string;
  download_url: string;
  source_file_variant: FmcsaSourceFileVariant;
  source_observed_at: string;
  source_task_id: string;
  source_schedule_id: string | null;
  source_run_metadata: Record<string, unknown>;
  artifact_bucket: string;
  artifact_path: string;
  row_count: number;
  artifact_checksum: string;
}

interface FmcsaArtifactIngestConfirmation {
  feed_name: string;
  table_name: string;
  feed_date: string;
  rows_received: number;
  rows_written: number;
  checksum_verified: boolean;
}

interface StorageFileObject {
  name: string;
  created_at: string;
}

interface SupabaseStorageClient {
  upload(bucket: string, path: string, data: Uint8Array, options?: { contentType?: string; upsert?: boolean }): Promise<{ error: Error | null }>;
  remove(bucket: string, paths: string[]): Promise<{ error: Error | null }>;
  createBucket(name: string, options?: { public: boolean }): Promise<{ error: Error | null }>;
  list(bucket: string, path: string): Promise<{ data: StorageFileObject[] | null; error: Error | null }>;
}

const MANIFEST_INGEST_TIMEOUT_MS = 1_800_000; // 30 minutes

interface ParsedRowsResult {
  rowsDownloaded: number;
  rowsParsed: number;
  rowsAccepted: number;
  rowsRejected: number;
  rows: FmcsaDailyDiffRow[];
}

const FMCSA_LONG_RUNNING_STREAM_TIMEOUTS = {
  // Streaming downloads stay open for the full ingest, not just the initial HTTP handshake.
  downloadTimeoutMs: 3_300_000,
  persistenceTimeoutMs: 300_000,
} as const;

const FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING = {
  useStreamingParser: true,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
} as const;

function shouldUseStreamingParser(feed: FmcsaDailyDiffFeedConfig): boolean {
  return (
    feed.useStreamingParser ??
    Boolean(feed.headerRow && feed.expectedContentTypes?.some((value) => value.includes("text/csv")))
  );
}

function resolveDownloadTimeoutMs(feed: FmcsaDailyDiffFeedConfig): number {
  return feed.downloadTimeoutMs ?? (shouldUseStreamingParser(feed) ? 300_000 : 60_000);
}

function resolvePersistenceTimeoutMs(feed: FmcsaDailyDiffFeedConfig): number | undefined {
  return feed.persistenceTimeoutMs ?? (shouldUseStreamingParser(feed) ? 120_000 : undefined);
}

function isAbortTimeoutError(error: unknown): error is Error {
  return error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError");
}

function formatStreamingWorkflowError(feed: FmcsaDailyDiffFeedConfig, error: unknown): Error {
  if (error instanceof InternalApiTimeoutError) {
    return new Error(
      `${feed.feedName} persistence request timed out after ${resolvePersistenceTimeoutMs(feed)}ms: ${error.path}`,
    );
  }

  if (error instanceof InternalApiError || error instanceof PersistenceConfirmationError) {
    return error;
  }

  if (isAbortTimeoutError(error)) {
    return new Error(
      `${feed.feedName} download stream timed out after ${resolveDownloadTimeoutMs(feed)}ms`,
    );
  }

  if (error instanceof Error) {
    return error.message.startsWith(`${feed.feedName} `)
      ? error
      : new Error(`${feed.feedName} CSV parsing failed: ${error.message}`);
  }

  return new Error(`${feed.feedName} CSV parsing failed: ${String(error)}`);
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
): ParsedRowsResult {
  if (rawBody.trim().length === 0) {
    throw new Error(`${feed.feedName} download returned an empty body`);
  }
  if (rawBody.trimStart().toLowerCase().startsWith("<!doctype html") || rawBody.includes("<html")) {
    throw new Error(`${feed.feedName} download returned HTML instead of CSV data`);
  }

  let parsedRecords: unknown;
  try {
    parsedRecords = parseCsvSync(rawBody, {
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
    validateHeaderRow(
      feed,
      ensureStringArray(parsedRecords[0], `${feed.feedName} header row is not a CSV value array`),
    );

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

    try {
      normalizedRows.push(normalizeCsvRow(feed, values, rowNumber));
    } catch {
      rejectedRows.push({ rowNumber, width: values.length });
    }
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

function validateHeaderRow(feed: FmcsaDailyDiffFeedConfig, headerRow: string[]): void {
  if (!feed.headerRow) {
    return;
  }

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
}

function normalizeCsvRow(
  feed: FmcsaDailyDiffFeedConfig,
  values: string[],
  rowNumber: number,
): FmcsaDailyDiffRow {
  if (values.length !== feed.expectedFieldCount) {
    throw new Error(
      `${feed.feedName} row width validation failed: expected ${feed.expectedFieldCount} columns; row ${rowNumber} width ${values.length}`,
    );
  }

  const rawFields: Record<string, string> = {};
  feed.sourceFields.forEach((fieldName, fieldIndex) => {
    rawFields[fieldName] = values[fieldIndex] ?? "";
  });

  return {
    row_number: rowNumber,
    raw_values: values,
    raw_fields: rawFields,
  };
}

function validateDownloadResponse(response: Response, feed: FmcsaDailyDiffFeedConfig): void {
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
}

async function downloadDailyDiffResponse(
  fetchImpl: typeof fetch,
  feed: FmcsaDailyDiffFeedConfig,
): Promise<Response> {
  let response: Response;
  const timeoutMs = resolveDownloadTimeoutMs(feed);
  try {
    response = await fetchImpl(feed.downloadUrl, {
      method: "GET",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    throw new Error(
      `${feed.feedName} download failed: ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  validateDownloadResponse(response, feed);
  return response;
}

async function downloadDailyDiffText(
  fetchImpl: typeof fetch,
  feed: FmcsaDailyDiffFeedConfig,
): Promise<string> {
  const response = await downloadDailyDiffResponse(fetchImpl, feed);
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

function createStorageClient(dependencies: FmcsaDailyDiffWorkflowDependencies): SupabaseStorageClient {
  if (dependencies.supabaseClient) {
    return dependencies.supabaseClient;
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const supabaseServiceKey = process.env.SUPABASE_SERVICE_KEY;
  if (!supabaseUrl || !supabaseServiceKey) {
    throw new Error("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set for artifact upload");
  }

  const client = createSupabaseClient(supabaseUrl, supabaseServiceKey);
  return {
    async upload(bucket: string, path: string, data: Uint8Array, options?: { contentType?: string; upsert?: boolean }) {
      // Use TUS resumable upload protocol — standard uploads are only reliable up to 6MB,
      // and most FMCSA artifacts exceed that (Company Census gzips to ~56MB).
      const uploadUrl = `${supabaseUrl}/storage/v1/upload/resumable`;
      const buffer = Buffer.from(data);
      return new Promise<{ error: Error | null }>((resolve) => {
        const tusUpload = new TusUpload(buffer, {
          endpoint: uploadUrl,
          retryDelays: [0, 3000, 5000, 10000, 20000],
          headers: {
            authorization: `Bearer ${supabaseServiceKey}`,
            apikey: supabaseServiceKey,
          },
          chunkSize: 6 * 1024 * 1024, // 6MB chunks
          metadata: {
            bucketName: bucket,
            objectName: path,
            contentType: options?.contentType ?? "application/octet-stream",
            cacheControl: "3600",
          },
          uploadSize: buffer.length,
          onError: (error) => {
            resolve({ error: new Error(`TUS upload failed for ${bucket}/${path}: ${error.message}`) });
          },
          onSuccess: () => {
            resolve({ error: null });
          },
        });
        tusUpload.start();
      });
    },
    async remove(bucket: string, paths: string[]) {
      const { error } = await client.storage.from(bucket).remove(paths);
      return { error };
    },
    async createBucket(name: string, options?: { public: boolean }) {
      const { error } = await client.storage.createBucket(name, options ?? { public: false });
      return { error };
    },
    async list(bucket: string, path: string) {
      const { data, error } = await client.storage.from(bucket).list(path);
      return { data: data as StorageFileObject[] | null, error };
    },
  };
}

function buildNdjsonGzipped(rows: FmcsaDailyDiffRow[]): { gzippedBytes: Uint8Array; checksum: string } {
  const ndjson = rows.map((row) => JSON.stringify(row)).join("\n") + "\n";
  const gzippedBytes = gzipSync(Buffer.from(ndjson, "utf-8"));
  const checksum = createHash("sha256").update(gzippedBytes).digest("hex");
  return { gzippedBytes, checksum };
}

function resolveArtifactPath(feed: FmcsaDailyDiffFeedConfig, feedDate: string): string {
  const sanitizedFeedName = feed.feedName.replace(/[^a-zA-Z0-9_-]/g, "_");
  const timestamp = Date.now();
  return `${sanitizedFeedName}/${feedDate}/${timestamp}.ndjson.gz`;
}

async function ensureBucketExists(storage: SupabaseStorageClient): Promise<void> {
  const { error } = await storage.createBucket(FMCSA_ARTIFACTS_BUCKET, { public: false });
  if (error && !error.message?.includes("already exists")) {
    throw new Error(`Failed to create bucket ${FMCSA_ARTIFACTS_BUCKET}: ${error.message}`);
  }
}

const ARTIFACT_TTL_DAYS = 7;

async function cleanupOldArtifacts(
  storage: SupabaseStorageClient,
  feed: FmcsaDailyDiffFeedConfig,
): Promise<void> {
  const sanitizedFeedName = feed.feedName.replace(/[^a-zA-Z0-9_-]/g, "_");
  try {
    // List date directories for this feed
    const { data: dateDirs, error: listError } = await storage.list(FMCSA_ARTIFACTS_BUCKET, sanitizedFeedName);
    if (listError || !dateDirs) {
      logger.warn("fmcsa artifact ttl list failed (non-fatal)", {
        feed_name: feed.feedName,
        error: listError?.message ?? "no data returned",
      });
      return;
    }

    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - ARTIFACT_TTL_DAYS);

    const expiredPaths: string[] = [];
    for (const dir of dateDirs) {
      const created = new Date(dir.created_at);
      if (created < cutoff) {
        // List files inside the expired date directory
        const { data: files } = await storage.list(FMCSA_ARTIFACTS_BUCKET, `${sanitizedFeedName}/${dir.name}`);
        if (files) {
          for (const file of files) {
            expiredPaths.push(`${sanitizedFeedName}/${dir.name}/${file.name}`);
          }
        }
      }
    }

    if (expiredPaths.length > 0) {
      const { error: removeError } = await storage.remove(FMCSA_ARTIFACTS_BUCKET, expiredPaths);
      if (removeError) {
        logger.warn("fmcsa artifact ttl cleanup failed (non-fatal)", {
          feed_name: feed.feedName,
          expired_count: expiredPaths.length,
          error: removeError.message,
        });
      } else {
        logger.info("fmcsa artifact ttl cleanup", {
          feed_name: feed.feedName,
          expired_artifacts_removed: expiredPaths.length,
        });
      }
    }
  } catch (err) {
    logger.warn("fmcsa artifact ttl cleanup error (non-fatal)", {
      feed_name: feed.feedName,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

async function uploadArtifactAndIngest(
  client: InternalApiClient,
  storage: SupabaseStorageClient,
  payload: FmcsaDailyDiffWorkflowPayload,
  rows: FmcsaDailyDiffRow[],
  feedDate: string,
  observedAt: string,
): Promise<FmcsaArtifactIngestConfirmation> {
  const { gzippedBytes, checksum } = buildNdjsonGzipped(rows);
  return uploadPrebuiltArtifactAndIngest(
    client,
    storage,
    payload,
    gzippedBytes,
    checksum,
    rows.length,
    feedDate,
    observedAt,
  );
}

async function uploadPrebuiltArtifactAndIngest(
  client: InternalApiClient,
  storage: SupabaseStorageClient,
  payload: FmcsaDailyDiffWorkflowPayload,
  gzippedBytes: Uint8Array,
  checksum: string,
  rowCount: number,
  feedDate: string,
  observedAt: string,
): Promise<FmcsaArtifactIngestConfirmation> {
  await ensureBucketExists(storage);

  const artifactPath = resolveArtifactPath(payload.feed, feedDate);

  logger.info("fmcsa artifact upload start", {
    feed_name: payload.feed.feedName,
    artifact_path: artifactPath,
    row_count: rowCount,
    artifact_size_bytes: gzippedBytes.length,
  });

  const { error: uploadError } = await storage.upload(
    FMCSA_ARTIFACTS_BUCKET,
    artifactPath,
    gzippedBytes,
    { contentType: "application/gzip", upsert: false },
  );
  if (uploadError) {
    throw new Error(`Failed to upload artifact to ${FMCSA_ARTIFACTS_BUCKET}/${artifactPath}: ${uploadError.message}`);
  }

  logger.info("fmcsa artifact uploaded", {
    feed_name: payload.feed.feedName,
    artifact_path: artifactPath,
    artifact_size_bytes: gzippedBytes.length,
    checksum,
  });

  const sourceRunMetadata = serializeSchedulePayload(payload.schedule, payload.feed, feedDate, observedAt);
  const manifest: FmcsaArtifactIngestManifest = {
    feed_name: payload.feed.feedName,
    feed_date: feedDate,
    download_url: payload.feed.downloadUrl,
    source_file_variant: payload.feed.sourceFileVariant,
    source_observed_at: observedAt,
    source_task_id: payload.feed.taskId,
    source_schedule_id: payload.schedule?.scheduleId ?? null,
    source_run_metadata: sourceRunMetadata,
    artifact_bucket: FMCSA_ARTIFACTS_BUCKET,
    artifact_path: artifactPath,
    row_count: rowCount,
    artifact_checksum: checksum,
  };

  const confirmation = await writeDedicatedTableConfirmed<FmcsaArtifactIngestConfirmation>(client, {
    path: "/api/internal/fmcsa/ingest-artifact",
    payload: manifest,
    timeoutMs: MANIFEST_INGEST_TIMEOUT_MS,
    validate: (response) =>
      isRecord(response) &&
      response.checksum_verified === true &&
      typeof response.rows_received === "number" &&
      typeof response.rows_written === "number" &&
      response.rows_received === rowCount &&
      response.rows_written >= 0,
    confirmationErrorMessage: `${payload.feed.feedName} artifact ingest confirmation failed`,
  });

  logger.info("fmcsa artifact ingest confirmed", {
    feed_name: confirmation.feed_name,
    table_name: confirmation.table_name,
    rows_received: confirmation.rows_received,
    rows_written: confirmation.rows_written,
  });

  // Clean up artifact after confirmed success
  try {
    const { error: deleteError } = await storage.remove(FMCSA_ARTIFACTS_BUCKET, [artifactPath]);
    if (deleteError) {
      logger.warn("fmcsa artifact delete failed (non-fatal)", {
        artifact_path: artifactPath,
        error: deleteError.message,
      });
    }
  } catch (deleteErr) {
    logger.warn("fmcsa artifact delete failed (non-fatal)", {
      artifact_path: artifactPath,
      error: deleteErr instanceof Error ? deleteErr.message : String(deleteErr),
    });
  }

  // TTL cleanup: remove artifacts older than 7 days for this feed
  await cleanupOldArtifacts(storage, payload.feed);

  return confirmation;
}

async function parseAndPersistStreamedCsv(
  client: InternalApiClient,
  storage: SupabaseStorageClient,
  payload: FmcsaDailyDiffWorkflowPayload,
  feedDate: string,
  observedAt: string,
  response: Response,
): Promise<FmcsaDailyDiffWorkflowResult> {
  if (!response.body) {
    throw new Error(`${payload.feed.feedName} download returned no response body`);
  }

  const parser = createCsvStreamParser({
    bom: true,
    columns: false,
    relax_column_count: true,
    skip_empty_lines: true,
    trim: false,
  });
  const inputStream = Readable.fromWeb(response.body as any);
  inputStream.pipe(parser);

  let headerValidated = false;
  let rowNumber = 0;
  let rowsDownloaded = 0;
  let rowsParsed = 0;
  let rowsAccepted = 0;

  // Write NDJSON lines to a temp file on disk instead of accumulating in memory.
  // This keeps memory usage O(1) regardless of feed size (critical for 2M+ row feeds).
  const ndjsonTmpPath = join(tmpdir(), `fmcsa-${payload.feed.feedName}-${Date.now()}.ndjson`);
  const ndjsonFileStream = createWriteStream(ndjsonTmpPath, { encoding: "utf-8" });

  try {
    for await (const record of parser) {
      const values = ensureStringArray(record, `${payload.feed.feedName} row is not a CSV value array`);
      if (payload.feed.headerRow && !headerValidated) {
        validateHeaderRow(payload.feed, values);
        headerValidated = true;
        continue;
      }

      rowNumber += 1;
      rowsDownloaded += 1;
      rowsParsed += 1;
      const line = JSON.stringify(normalizeCsvRow(payload.feed, values, rowNumber));
      const canContinue = ndjsonFileStream.write(line + "\n");
      rowsAccepted += 1;

      // Respect backpressure: if the write stream's internal buffer is full,
      // wait for it to drain before writing more. This prevents unbounded
      // memory accumulation for large feeds (2M+ rows).
      if (!canContinue) {
        await new Promise<void>((resolve) => ndjsonFileStream.once("drain", resolve));
      }

      if (rowsDownloaded % 500_000 === 0) {
        logger.info("fmcsa streaming parse progress", {
          feed_name: payload.feed.feedName,
          rows_downloaded: rowsDownloaded,
          rows_accepted: rowsAccepted,
        });
      }
    }
  } catch (error) {
    ndjsonFileStream.end();
    cleanupTmpFile(ndjsonTmpPath);
    throw formatStreamingWorkflowError(payload.feed, error);
  }

  // Close the NDJSON file stream and wait for flush
  await new Promise<void>((resolve, reject) => {
    ndjsonFileStream.end(() => resolve());
    ndjsonFileStream.on("error", reject);
  });

  if (payload.feed.headerRow && !headerValidated) {
    cleanupTmpFile(ndjsonTmpPath);
    throw new Error(`${payload.feed.feedName} download contained no parseable header row`);
  }
  if (payload.feed.headerRow && rowsDownloaded === 0) {
    cleanupTmpFile(ndjsonTmpPath);
    throw new Error(`${payload.feed.feedName} download contained a header row but no data rows`);
  }
  if (!payload.feed.headerRow && rowsDownloaded === 0) {
    cleanupTmpFile(ndjsonTmpPath);
    throw new Error(`${payload.feed.feedName} download contained no parseable rows`);
  }

  // Gzip the NDJSON file on disk via streaming pipeline — no full file in memory
  const gzippedTmpPath = ndjsonTmpPath + ".gz";
  try {
    await pipeline(
      createReadStream(ndjsonTmpPath),
      createGzip(),
      createWriteStream(gzippedTmpPath),
    );
  } finally {
    cleanupTmpFile(ndjsonTmpPath);
  }

  // Read the gzipped file and compute checksum — gzipped files are much smaller than raw NDJSON
  const { readFile } = await import("node:fs/promises");
  const gzippedBytes = await readFile(gzippedTmpPath);
  const checksum = createHash("sha256").update(gzippedBytes).digest("hex");

  logger.info("fmcsa artifact built on disk", {
    feed_name: payload.feed.feedName,
    rows_accepted: rowsAccepted,
    gzipped_size_mb: Math.round(gzippedBytes.length / 1_048_576 * 100) / 100,
  });

  let confirmation: FmcsaArtifactIngestConfirmation;
  try {
    confirmation = await uploadPrebuiltArtifactAndIngest(
      client, storage, payload, gzippedBytes, checksum, rowsAccepted, feedDate, observedAt,
    );
  } finally {
    cleanupTmpFile(gzippedTmpPath);
  }

  return {
    feed_name: payload.feed.feedName,
    feed_date: feedDate,
    download_url: payload.feed.downloadUrl,
    source_file_variant: payload.feed.sourceFileVariant,
    observed_at: observedAt,
    rows_downloaded: rowsDownloaded,
    rows_parsed: rowsParsed,
    rows_accepted: rowsAccepted,
    rows_rejected: 0,
    rows_written: confirmation.rows_written,
  };
}

function cleanupTmpFile(path: string): void {
  try {
    unlinkSync(path);
  } catch {
    // File may not exist if cleanup already happened
  }
}

export async function runFmcsaDailyDiffWorkflow(
  payload: FmcsaDailyDiffWorkflowPayload,
  dependencies: FmcsaDailyDiffWorkflowDependencies = {},
): Promise<FmcsaDailyDiffWorkflowResult> {
  const client = createClient(payload, dependencies);
  const storage = createStorageClient(dependencies);
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

  if (shouldUseStreamingParser(payload.feed)) {
    const response = await downloadDailyDiffResponse(fetchImpl, payload.feed);
    const result = await parseAndPersistStreamedCsv(
      client,
      storage,
      payload,
      feedDate,
      observedAt,
      response,
    );
    logger.info("fmcsa snapshot workflow succeeded", { ...result });
    return result;
  }

  const rawBody = await downloadDailyDiffText(fetchImpl, payload.feed);
  const parsed = parseDailyDiffBody(payload.feed, rawBody);
  const confirmation = await uploadArtifactAndIngest(client, storage, payload, parsed.rows, feedDate, observedAt);

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
    rows_written: confirmation.rows_written,
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
  ...FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING,
};

export const FMCSA_BOC3_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "BOC3 - All With History",
  downloadUrl: "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain",
  taskId: "fmcsa-boc3-all-history",
  internalUpsertPath: "/api/internal/process-agent-filings/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_BOC3_DAILY_FEED.sourceFields],
  expectedFieldCount: 9,
  ...FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING,
};

export const FMCSA_ACTPENDINSUR_ALL_HISTORY_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "ActPendInsur - All With History",
  downloadUrl: "https://data.transportation.gov/download/y77m-3nfx/text%2Fplain",
  taskId: "fmcsa-actpendinsur-all-history",
  internalUpsertPath: "/api/internal/insurance-policy-filings/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: [...FMCSA_ACTPENDINSUR_DAILY_FEED.sourceFields],
  expectedFieldCount: 11,
  ...FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING,
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
  ...FMCSA_PLAIN_TEXT_ALL_HISTORY_STREAMING,
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

const FMCSA_CRASH_FILE_SOURCE_FIELDS = [
  "CHANGE_DATE",
  "CRASH_ID",
  "REPORT_STATE",
  "REPORT_NUMBER",
  "REPORT_DATE",
  "REPORT_TIME",
  "REPORT_SEQ_NO",
  "DOT_NUMBER",
  "CI_STATUS_CODE",
  "FINAL_STATUS_DATE",
  "LOCATION",
  "CITY_CODE",
  "CITY",
  "STATE",
  "COUNTY_CODE",
  "TRUCK_BUS_IND",
  "TRAFFICWAY_ID",
  "ACCESS_CONTROL_ID",
  "ROAD_SURFACE_CONDITION_ID",
  "CARGO_BODY_TYPE_ID",
  "GVW_RATING_ID",
  "VEHICLE_IDENTIFICATION_NUMBER",
  "VEHICLE_LICENSE_NUMBER",
  "VEHICLE_LIC_STATE",
  "VEHICLE_HAZMAT_PLACARD",
  "WEATHER_CONDITION_ID",
  "VEHICLE_CONFIGURATION_ID",
  "LIGHT_CONDITION_ID",
  "HAZMAT_RELEASED",
  "AGENCY",
  "VEHICLES_IN_ACCIDENT",
  "FATALITIES",
  "INJURIES",
  "TOW_AWAY",
  "FEDERAL_RECORDABLE",
  "STATE_RECORDABLE",
  "SNET_VERSION_NUMBER",
  "SNET_SEQUENCE_ID",
  "TRANSACTION_CODE",
  "TRANSACTION_DATE",
  "UPLOAD_FIRST_BYTE",
  "UPLOAD_DOT_NUMBER",
  "UPLOAD_SEARCH_INDICATOR",
  "UPLOAD_DATE",
  "ADD_DATE",
  "CRASH_CARRIER_ID",
  "CRASH_CARRIER_NAME",
  "CRASH_CARRIER_STREET",
  "CRASH_CARRIER_CITY",
  "CRASH_CARRIER_CITY_CODE",
  "CRASH_CARRIER_STATE",
  "CRASH_CARRIER_ZIP_CODE",
  "CRASH_COLONIA",
  "DOCKET_NUMBER",
  "CRASH_CARRIER_INTERSTATE",
  "NO_ID_FLAG",
  "STATE_NUMBER",
  "STATE_ISSUING_NUMBER",
  "CRASH_EVENT_SEQ_ID_DESC",
] as const;

const FMCSA_CARRIER_ALL_HISTORY_SOURCE_FIELDS = [
  ...FMCSA_CARRIER_DAILY_FEED.sourceFields,
] as const;

const FMCSA_CARRIER_ALL_HISTORY_HEADERS = [
  "DOCKET_NUMBER",
  "DOT_NUMBER",
  "MX_TYPE",
  "RFC_NUMBER",
  "COMMON_STAT",
  "CONTRACT_STAT",
  "BROKER_STAT",
  "COMMON_APP_PEND",
  "CONTRACT_APP_PEND",
  "BROKER_APP_PEND",
  "COMMON_REV_PEND",
  "CONTRACT_REV_PEND",
  "BROKER_REV_PEND",
  "PROPERTY_CHK",
  "PASSENGER_CHK",
  "HHG_CHK",
  "PRIVATE_AUTH_CHK",
  "ENTERPRISE_CHK",
  "MIN_COV_AMOUNT",
  "CARGO_REQ",
  "BOND_REQ",
  "BIPD_FILE",
  "CARGO_FILE",
  "BOND_FILE",
  "UNDELIVERABLE_MAIL",
  "DBA_NAME",
  "LEGAL_NAME",
  "BUS_STREET_PO",
  "BUS_COLONIA",
  "BUS_CITY",
  "BUS_STATE_CODE",
  "BUS_CTRY_CODE",
  "BUS_ZIP_CODE",
  "BUS_TELNO",
  "BUS_FAX",
  "MAIL_STREET_PO",
  "MAIL_COLONIA",
  "MAIL_CITY",
  "MAIL_STATE_CODE",
  "MAIL_CTRY_CODE",
  "MAIL_ZIP_CODE",
  "MAIL_TELNO",
  "MAIL_FAX",
] as const;

const FMCSA_INSPECTION_UNITS_SOURCE_FIELDS = [
  "CHANGE_DATE",
  "INSPECTION_ID",
  "INSP_UNIT_ID",
  "INSP_UNIT_TYPE_ID",
  "INSP_UNIT_NUMBER",
  "INSP_UNIT_MAKE",
  "INSP_UNIT_COMPANY",
  "INSP_UNIT_LICENSE",
  "INSP_UNIT_LICENSE_STATE",
  "INSP_UNIT_VEHICLE_ID_NUMBER",
  "INSP_UNIT_DECAL",
  "INSP_UNIT_DECAL_NUMBER",
] as const;

const FMCSA_SPECIAL_STUDIES_SOURCE_FIELDS = [
  "CHANGE_DATE",
  "INSPECTION_ID",
  "INSP_STUDY_ID",
  "STUDY",
  "SEQ_NO",
] as const;

const FMCSA_REVOCATION_ALL_HISTORY_SOURCE_FIELDS = [
  ...FMCSA_REVOCATION_DAILY_FEED.sourceFields,
] as const;

const FMCSA_REVOCATION_ALL_HISTORY_HEADERS = [
  "DOCKET_NUMBER",
  "DOT_NUMBER",
  "TYPE_LICENSE",
  "ORDER1_SERVE_DATE",
  "ORDER2_TYPE_DESC",
  "order2_effective_Date",
] as const;

const FMCSA_INSUR_ALL_HISTORY_SOURCE_FIELDS = [
  ...FMCSA_INSURANCE_DAILY_FEED.sourceFields,
] as const;

const FMCSA_INSUR_ALL_HISTORY_HEADERS = [
  "prefix_docket_number",
  "ins_type_code",
  "ins_class_code",
  "max_cov_amount",
  "underl_lim_amount",
  "policy_no",
  "effective_date",
  "ins_form_code",
  "name_company",
] as const;

const FMCSA_OUT_OF_SERVICE_ORDER_SOURCE_FIELDS = [
  "DOT_NUMBER",
  "LEGAL_NAME",
  "DBA_NAME",
  "OOS_DATE",
  "OOS_REASON",
  "STATUS",
  "OOS_RESCIND_DATE",
] as const;

const FMCSA_OUT_OF_SERVICE_ORDER_HEADERS = [
  "DOT_NUMBER",
  "LEGAL_NAME",
  "DBA_NAME",
  "OOS_DATE",
  "OOS_REASON",
  "STATUS",
  "RESCIND_DATE",
] as const;

const FMCSA_INSPECTION_CITATIONS_SOURCE_FIELDS = [
  "CHANGE_DATE",
  "INSPECTION_ID",
  "VIOSEQNUM",
  "ADJSEQ",
  "CITATION_CODE",
  "CITATION_RESULT",
] as const;

const FMCSA_VEHICLE_INSPECTION_VIOLATIONS_SOURCE_FIELDS = [
  "CHANGE_DATE",
  "INSPECTION_ID",
  "INSP_VIOLATION_ID",
  "SEQ_NO",
  "PART_NO",
  "PART_NO_SECTION",
  "INSP_VIOL_UNIT",
  "INSP_UNIT_ID",
  "INSP_VIOLATION_CATEGORY_ID",
  "OUT_OF_SERVICE_INDICATOR",
  "DEFECT_VERIFICATION_ID",
  "CITATION_NUMBER",
] as const;

const FMCSA_COMPANY_CENSUS_SOURCE_FIELDS = [
  "MCS150_DATE",
  "ADD_DATE",
  "STATUS_CODE",
  "DOT_NUMBER",
  "DUN_BRADSTREET_NO",
  "PHY_OMC_REGION",
  "SAFETY_INV_TERR",
  "CARRIER_OPERATION",
  "BUSINESS_ORG_ID",
  "MCS150_MILEAGE",
  "MCS150_MILEAGE_YEAR",
  "MCS151_MILEAGE",
  "TOTAL_CARS",
  "MCS150_UPDATE_CODE_ID",
  "PRIOR_REVOKE_FLAG",
  "PRIOR_REVOKE_DOT_NUMBER",
  "PHONE",
  "FAX",
  "CELL_PHONE",
  "COMPANY_OFFICER_1",
  "COMPANY_OFFICER_2",
  "BUSINESS_ORG_DESC",
  "TRUCK_UNITS",
  "POWER_UNITS",
  "BUS_UNITS",
  "FLEETSIZE",
  "REVIEW_ID",
  "RECORDABLE_CRASH_RATE",
  "MAIL_NATIONALITY_INDICATOR",
  "PHY_NATIONALITY_INDICATOR",
  "PHY_BARRIO",
  "MAIL_BARRIO",
  "CARSHIP",
  "DOCKET1PREFIX",
  "DOCKET1",
  "DOCKET2PREFIX",
  "DOCKET2",
  "DOCKET3PREFIX",
  "DOCKET3",
  "POINTNUM",
  "TOTAL_INTRASTATE_DRIVERS",
  "MCSIPSTEP",
  "MCSIPDATE",
  "HM_Ind",
  "INTERSTATE_BEYOND_100_MILES",
  "INTERSTATE_WITHIN_100_MILES",
  "INTRASTATE_BEYOND_100_MILES",
  "INTRASTATE_WITHIN_100_MILES",
  "TOTAL_CDL",
  "TOTAL_DRIVERS",
  "AVG_DRIVERS_LEASED_PER_MONTH",
  "CLASSDEF",
  "LEGAL_NAME",
  "DBA_NAME",
  "PHY_STREET",
  "PHY_CITY",
  "PHY_COUNTRY",
  "PHY_STATE",
  "PHY_ZIP",
  "PHY_CNTY",
  "CARRIER_MAILING_STREET",
  "CARRIER_MAILING_STATE",
  "CARRIER_MAILING_CITY",
  "CARRIER_MAILING_COUNTRY",
  "CARRIER_MAILING_ZIP",
  "CARRIER_MAILING_CNTY",
  "CARRIER_MAILING_UND_DATE",
  "DRIVER_INTER_TOTAL",
  "EMAIL_ADDRESS",
  "REVIEW_TYPE",
  "REVIEW_DATE",
  "SAFETY_RATING",
  "SAFETY_RATING_DATE",
  "UNDELIV_PHY",
  "CRGO_GENFREIGHT",
  "CRGO_HOUSEHOLD",
  "CRGO_METALSHEET",
  "CRGO_MOTOVEH",
  "CRGO_DRIVETOW",
  "CRGO_LOGPOLE",
  "CRGO_BLDGMAT",
  "CRGO_MOBILEHOME",
  "CRGO_MACHLRG",
  "CRGO_PRODUCE",
  "CRGO_LIQGAS",
  "CRGO_INTERMODAL",
  "CRGO_PASSENGERS",
  "CRGO_OILFIELD",
  "CRGO_LIVESTOCK",
  "CRGO_GRAINFEED",
  "CRGO_COALCOKE",
  "CRGO_MEAT",
  "CRGO_GARBAGE",
  "CRGO_USMAIL",
  "CRGO_CHEM",
  "CRGO_DRYBULK",
  "CRGO_COLDFOOD",
  "CRGO_BEVERAGES",
  "CRGO_PAPERPROD",
  "CRGO_UTILITY",
  "CRGO_FARMSUPP",
  "CRGO_CONSTRUCT",
  "CRGO_WATERWELL",
  "CRGO_CARGOOTHR",
  "CRGO_CARGOOTHR_DESC",
  "OWNTRUCK",
  "OWNTRACT",
  "OWNTRAIL",
  "OWNCOACH",
  "OWNSCHOOL_1_8",
  "OWNSCHOOL_9_15",
  "OWNSCHOOL_16",
  "OWNBUS_16",
  "OWNVAN_1_8",
  "OWNVAN_9_15",
  "OWNLIMO_1_8",
  "OWNLIMO_9_15",
  "OWNLIMO_16",
  "TRMTRUCK",
  "TRMTRACT",
  "TRMTRAIL",
  "TRMCOACH",
  "TRMSCHOOL_1_8",
  "TRMSCHOOL_9_15",
  "TRMSCHOOL_16",
  "TRMBUS_16",
  "TRMVAN_1_8",
  "TRMVAN_9_15",
  "TRMLIMO_1_8",
  "TRMLIMO_9_15",
  "TRMLIMO_16",
  "TRPTRUCK",
  "TRPTRACT",
  "TRPTRAIL",
  "TRPCOACH",
  "TRPSCHOOL_1_8",
  "TRPSCHOOL_9_15",
  "TRPSCHOOL_16",
  "TRPBUS_16",
  "TRPVAN_1_8",
  "TRPVAN_9_15",
  "TRPLIMO_1_8",
  "TRPLIMO_9_15",
  "TRPLIMO_16",
  "DOCKET1_STATUS_CODE",
  "DOCKET2_STATUS_CODE",
  "DOCKET3_STATUS_CODE",
] as const;

const FMCSA_VEHICLE_INSPECTION_FILE_SOURCE_FIELDS = [
  "CHANGE_DATE",
  "INSPECTION_ID",
  "DOT_NUMBER",
  "REPORT_STATE",
  "REPORT_NUMBER",
  "INSP_DATE",
  "INSP_START_TIME",
  "INSP_END_TIME",
  "REGISTRATION_DATE",
  "REGION",
  "CI_STATUS_CODE",
  "LOCATION",
  "LOCATION_DESC",
  "COUNTY_CODE_STATE",
  "COUNTY_CODE",
  "INSP_LEVEL_ID",
  "SERVICE_CENTER",
  "CENSUS_SOURCE_ID",
  "INSP_FACILITY",
  "SHIPPER_NAME",
  "SHIPPING_PAPER_NUMBER",
  "CARGO_TANK",
  "HAZMAT_PLACARD_REQ",
  "SNET_VERSION_NUMBER",
  "SNET_SEARCH_DATE",
  "ALCOHOL_CONTROL_SUB",
  "DRUG_INTRDCTN_SEARCH",
  "DRUG_INTRDCTN_ARRESTS",
  "SIZE_WEIGHT_ENF",
  "TRAFFIC_ENF",
  "LOCAL_ENF_JURISDICTION",
  "PEN_CEN_MATCH",
  "FINAL_STATUS_DATE",
  "POST_ACC_IND",
  "GROSS_COMB_VEH_WT",
  "VIOL_TOTAL",
  "OOS_TOTAL",
  "DRIVER_VIOL_TOTAL",
  "DRIVER_OOS_TOTAL",
  "VEHICLE_VIOL_TOTAL",
  "VEHICLE_OOS_TOTAL",
  "HAZMAT_VIOL_TOTAL",
  "HAZMAT_OOS_TOTAL",
  "SNET_SEQUENCE_ID",
  "TRANSACTION_CODE",
  "TRANSACTION_DATE",
  "UPLOAD_DATE",
  "UPLOAD_FIRST_BYTE",
  "UPLOAD_DOT_NUMBER",
  "UPLOAD_SEARCH_INDICATOR",
  "CENSUS_SEARCH_DATE",
  "SNET_INPUT_DATE",
  "SOURCE_OFFICE",
  "MCMIS_ADD_DATE",
  "INSP_CARRIER_NAME",
  "INSP_CARRIER_STREET",
  "INSP_CARRIER_CITY",
  "INSP_CARRIER_STATE",
  "INSP_CARRIER_ZIP_CODE",
  "INSP_COLONIA",
  "DOCKET_NUMBER",
  "INSP_INTERSTATE",
  "INSP_CARRIER_STATE_ID",
] as const;

export const FMCSA_CRASH_FILE_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Crash File",
  downloadUrl: "https://data.transportation.gov/api/views/aayw-vxb3/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-crash-file-daily",
  internalUpsertPath: "/api/internal/commercial-vehicle-crashes/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_CRASH_FILE_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_CRASH_FILE_SOURCE_FIELDS.length,
  headerRow: FMCSA_CRASH_FILE_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_CARRIER_ALL_HISTORY_CSV_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Carrier - All With History",
  downloadUrl: "https://data.transportation.gov/api/views/6eyk-hxee/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-carrier-all-history-daily",
  internalUpsertPath: "/api/internal/carrier-registrations/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: FMCSA_CARRIER_ALL_HISTORY_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_CARRIER_ALL_HISTORY_SOURCE_FIELDS.length,
  headerRow: FMCSA_CARRIER_ALL_HISTORY_HEADERS,
  expectedContentTypes: ["text/csv"],
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_INSPECTIONS_PER_UNIT_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Inspections Per Unit",
  downloadUrl: "https://data.transportation.gov/api/views/wt8s-2hbx/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-inspections-per-unit-daily",
  internalUpsertPath: "/api/internal/vehicle-inspection-units/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_INSPECTION_UNITS_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_INSPECTION_UNITS_SOURCE_FIELDS.length,
  headerRow: FMCSA_INSPECTION_UNITS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 1250,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_SPECIAL_STUDIES_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Special Studies",
  downloadUrl: "https://data.transportation.gov/api/views/5qik-smay/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-special-studies-daily",
  internalUpsertPath: "/api/internal/vehicle-inspection-special-studies/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_SPECIAL_STUDIES_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_SPECIAL_STUDIES_SOURCE_FIELDS.length,
  headerRow: FMCSA_SPECIAL_STUDIES_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 2500,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Revocation - All With History",
  downloadUrl: "https://data.transportation.gov/api/views/sa6p-acbp/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-revocation-all-history-daily",
  internalUpsertPath: "/api/internal/operating-authority-revocations/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: FMCSA_REVOCATION_ALL_HISTORY_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_REVOCATION_ALL_HISTORY_SOURCE_FIELDS.length,
  headerRow: FMCSA_REVOCATION_ALL_HISTORY_HEADERS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 2500,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_INSUR_ALL_HISTORY_CSV_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Insur - All With History",
  downloadUrl: "https://data.transportation.gov/api/views/ypjt-5ydn/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-insur-all-history-daily",
  internalUpsertPath: "/api/internal/insurance-policies/upsert-batch",
  sourceFileVariant: "all_with_history",
  sourceFields: FMCSA_INSUR_ALL_HISTORY_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_INSUR_ALL_HISTORY_SOURCE_FIELDS.length,
  headerRow: FMCSA_INSUR_ALL_HISTORY_HEADERS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 1250,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_OUT_OF_SERVICE_ORDERS_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "OUT OF SERVICE ORDERS",
  downloadUrl: "https://data.transportation.gov/api/views/p2mt-9ige/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-out-of-service-orders-daily",
  internalUpsertPath: "/api/internal/out-of-service-orders/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_OUT_OF_SERVICE_ORDER_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_OUT_OF_SERVICE_ORDER_SOURCE_FIELDS.length,
  headerRow: FMCSA_OUT_OF_SERVICE_ORDER_HEADERS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 2500,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_INSPECTIONS_AND_CITATIONS_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Inspections and Citations",
  downloadUrl: "https://data.transportation.gov/api/views/qbt8-7vic/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-inspections-citations-daily",
  internalUpsertPath: "/api/internal/vehicle-inspection-citations/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_INSPECTION_CITATIONS_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_INSPECTION_CITATIONS_SOURCE_FIELDS.length,
  headerRow: FMCSA_INSPECTION_CITATIONS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
};

export const FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Vehicle Inspections and Violations",
  downloadUrl: "https://data.transportation.gov/api/views/876r-jsdb/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-vehicle-inspections-violations-daily",
  internalUpsertPath: "/api/internal/carrier-inspection-violations/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_VEHICLE_INSPECTION_VIOLATIONS_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_VEHICLE_INSPECTION_VIOLATIONS_SOURCE_FIELDS.length,
  headerRow: FMCSA_VEHICLE_INSPECTION_VIOLATIONS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_COMPANY_CENSUS_FILE_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Company Census File",
  downloadUrl: "https://data.transportation.gov/api/views/az4n-8mr2/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-company-census-file-daily",
  internalUpsertPath: "/api/internal/motor-carrier-census-records/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_COMPANY_CENSUS_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_COMPANY_CENSUS_SOURCE_FIELDS.length,
  headerRow: FMCSA_COMPANY_CENSUS_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
  useStreamingParser: true,
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_VEHICLE_INSPECTION_FILE_FEED: FmcsaDailyDiffFeedConfig = {
  feedName: "Vehicle Inspection File",
  downloadUrl: "https://data.transportation.gov/api/views/fx4q-ay7w/rows.csv?accessType=DOWNLOAD",
  taskId: "fmcsa-vehicle-inspection-file-daily",
  internalUpsertPath: "/api/internal/carrier-inspections/upsert-batch",
  sourceFileVariant: "csv_export",
  sourceFields: FMCSA_VEHICLE_INSPECTION_FILE_SOURCE_FIELDS,
  expectedFieldCount: FMCSA_VEHICLE_INSPECTION_FILE_SOURCE_FIELDS.length,
  headerRow: FMCSA_VEHICLE_INSPECTION_FILE_SOURCE_FIELDS,
  expectedContentTypes: ["text/csv"],
  useStreamingParser: true,
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
};

export const FMCSA_REMAINING_CSV_EXPORT_FEEDS = [
  FMCSA_CRASH_FILE_FEED,
  FMCSA_CARRIER_ALL_HISTORY_CSV_FEED,
  FMCSA_INSPECTIONS_PER_UNIT_FEED,
  FMCSA_SPECIAL_STUDIES_FEED,
  FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED,
  FMCSA_INSUR_ALL_HISTORY_CSV_FEED,
  FMCSA_OUT_OF_SERVICE_ORDERS_FEED,
  FMCSA_INSPECTIONS_AND_CITATIONS_FEED,
  FMCSA_VEHICLE_INSPECTIONS_AND_VIOLATIONS_FEED,
  FMCSA_COMPANY_CENSUS_FILE_FEED,
  FMCSA_VEHICLE_INSPECTION_FILE_FEED,
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
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
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
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
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
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
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
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
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
  writeBatchSize: 10000,
  ...FMCSA_LONG_RUNNING_STREAM_TIMEOUTS,
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
  buildNdjsonGzipped,
  formatStreamingWorkflowError,
  parseDailyDiffBody,
  resolveFeedDate,
  resolveDownloadTimeoutMs,
  resolvePersistenceTimeoutMs,
  serializeSchedulePayload,
};
