import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";
import { gunzipSync } from "node:zlib";

import { createInternalApiClient } from "../internal-api.js";
import {
  __testables,
  FMCSA_ARTIFACTS_BUCKET,
  FMCSA_REVOCATION_DAILY_FEED,
  FMCSA_AUTHHIST_DAILY_FEED,
  type FmcsaDailyDiffRow,
  runFmcsaDailyDiffWorkflow,
} from "../fmcsa-daily-diff.js";

const { buildNdjsonGzipped } = __testables;

// --- Mock helpers ---

interface UploadCall {
  bucket: string;
  path: string;
  data: Uint8Array;
  options?: { contentType?: string; upsert?: boolean };
}

interface RemoveCall {
  bucket: string;
  paths: string[];
}

function createMockStorageClient(opts?: { uploadError?: Error; removeError?: Error }) {
  const uploads: UploadCall[] = [];
  const removes: RemoveCall[] = [];
  const bucketCreations: string[] = [];

  return {
    client: {
      async upload(bucket: string, path: string, data: Uint8Array, options?: { contentType?: string; upsert?: boolean }) {
        uploads.push({ bucket, path, data, options });
        return { error: opts?.uploadError ?? null };
      },
      async remove(bucket: string, paths: string[]) {
        removes.push({ bucket, paths });
        return { error: opts?.removeError ?? null };
      },
      async createBucket(name: string, _options?: { public: boolean }) {
        bucketCreations.push(name);
        return { error: null };
      },
      async list(_bucket: string, _path: string) {
        return { data: [], error: null };
      },
    },
    uploads,
    removes,
    bucketCreations,
  };
}

function createDownloadFetch(text: string): typeof fetch {
  return (async () => {
    return new Response(text, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }) as typeof fetch;
}

function createManifestCapturingFetch(params: {
  requests: Array<{ path: string; body: Record<string, unknown> | null }>;
  confirmationResponse: Record<string, unknown>;
}): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    const path = url.pathname;

    // The internal API client gzips the body, so decompress it
    let body: Record<string, unknown> | null = null;
    if (init?.body instanceof Uint8Array || Buffer.isBuffer(init?.body)) {
      try {
        const decompressed = gunzipSync(init.body as Uint8Array);
        body = JSON.parse(decompressed.toString("utf-8")) as Record<string, unknown>;
      } catch {
        body = null;
      }
    }

    params.requests.push({ path, body });

    return new Response(
      JSON.stringify({ data: params.confirmationResponse }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as typeof fetch;
}

// --- Tests ---

test("buildNdjsonGzipped produces valid gzipped NDJSON with correct checksum", () => {
  const rows: FmcsaDailyDiffRow[] = [
    { row_number: 1, raw_values: ["a", "b"], raw_fields: { col1: "a", col2: "b" } },
    { row_number: 2, raw_values: ["c", "d"], raw_fields: { col1: "c", col2: "d" } },
  ];

  const { gzippedBytes, checksum } = buildNdjsonGzipped(rows);

  // Verify checksum matches SHA-256 of gzipped bytes
  const expectedChecksum = createHash("sha256").update(gzippedBytes).digest("hex");
  assert.equal(checksum, expectedChecksum);

  // Decompress and verify NDJSON format
  const decompressed = gunzipSync(gzippedBytes).toString("utf-8");
  const lines = decompressed.trim().split("\n");
  assert.equal(lines.length, 2);

  const parsed0 = JSON.parse(lines[0]);
  assert.equal(parsed0.row_number, 1);
  assert.deepEqual(parsed0.raw_values, ["a", "b"]);
  assert.deepEqual(parsed0.raw_fields, { col1: "a", col2: "b" });

  const parsed1 = JSON.parse(lines[1]);
  assert.equal(parsed1.row_number, 2);
  assert.deepEqual(parsed1.raw_values, ["c", "d"]);
});

test("workflow uploads artifact and sends manifest POST with correct fields", async () => {
  const internalRequests: Array<{ path: string; body: Record<string, unknown> | null }> = [];
  const storage = createMockStorageClient();

  const confirmationResponse = {
    feed_name: "Revocation",
    table_name: "operating_authority_revocations",
    feed_date: "2026-03-10",
    rows_received: 2,
    rows_written: 2,
    checksum_verified: true,
  };

  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createManifestCapturingFetch({
      requests: internalRequests,
      confirmationResponse,
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
      supabaseClient: storage.client,
      fetchImpl: createDownloadFetch(
        [
          '"MC123456","12345678","Broker","03/08/2026","Insurance","03/10/2026"',
          '"FF222222","22223333","Common","03/09/2026","Safety","03/11/2026"',
        ].join("\n"),
      ),
    },
  );

  // Verify workflow result
  assert.equal(result.feed_name, "Revocation");
  assert.equal(result.rows_written, 2);
  assert.equal(result.rows_accepted, 2);

  // Verify artifact was uploaded to correct bucket
  assert.equal(storage.uploads.length, 1);
  assert.equal(storage.uploads[0].bucket, FMCSA_ARTIFACTS_BUCKET);
  assert.ok(storage.uploads[0].path.startsWith("Revocation/2026-03-10/"));
  assert.ok(storage.uploads[0].path.endsWith(".ndjson.gz"));

  // Verify uploaded artifact is valid gzipped NDJSON
  const decompressed = gunzipSync(storage.uploads[0].data).toString("utf-8");
  const lines = decompressed.trim().split("\n");
  assert.equal(lines.length, 2);
  const row0 = JSON.parse(lines[0]);
  assert.equal(row0.row_number, 1);
  assert.ok(Array.isArray(row0.raw_values));
  assert.ok(typeof row0.raw_fields === "object");

  // Verify manifest POST was sent to correct path
  assert.equal(internalRequests.length, 1);
  assert.equal(internalRequests[0].path, "/api/internal/fmcsa/ingest-artifact");

  // Verify manifest fields
  const manifest = internalRequests[0].body!;
  assert.equal(manifest.feed_name, "Revocation");
  assert.equal(manifest.feed_date, "2026-03-10");
  assert.equal(manifest.artifact_bucket, FMCSA_ARTIFACTS_BUCKET);
  assert.ok(typeof manifest.artifact_path === "string");
  assert.equal(manifest.row_count, 2);
  assert.ok(typeof manifest.artifact_checksum === "string");
  assert.equal((manifest.artifact_checksum as string).length, 64); // SHA-256 hex

  // Verify checksum in manifest matches uploaded artifact
  const expectedChecksum = createHash("sha256").update(storage.uploads[0].data).digest("hex");
  assert.equal(manifest.artifact_checksum, expectedChecksum);
});

test("workflow deletes artifact after confirmed success", async () => {
  const storage = createMockStorageClient();

  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createManifestCapturingFetch({
      requests: [],
      confirmationResponse: {
        feed_name: "AuthHist",
        table_name: "operating_authority_histories",
        feed_date: "2026-03-10",
        rows_received: 1,
        rows_written: 1,
        checksum_verified: true,
      },
    }),
  });

  await runFmcsaDailyDiffWorkflow(
    {
      feed: FMCSA_AUTHHIST_DAILY_FEED,
      schedule: {
        timestamp: "2026-03-10T15:00:00.000Z",
        scheduleId: "schedule-1",
        timezone: "America/New_York",
      },
    },
    {
      client,
      supabaseClient: storage.client,
      fetchImpl: createDownloadFetch(
        '"DK12345","999999","01","Authority Type","Action Desc","03/01/2026","03/10/2026","Filed","Pending"',
      ),
    },
  );

  // Verify artifact was deleted after success
  assert.equal(storage.removes.length, 1);
  assert.equal(storage.removes[0].bucket, FMCSA_ARTIFACTS_BUCKET);
  assert.equal(storage.removes[0].paths.length, 1);
  assert.equal(storage.removes[0].paths[0], storage.uploads[0].path);
});

test("workflow does not fail if artifact deletion fails", async () => {
  const storage = createMockStorageClient({ removeError: new Error("Storage unavailable") });

  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createManifestCapturingFetch({
      requests: [],
      confirmationResponse: {
        feed_name: "AuthHist",
        table_name: "operating_authority_histories",
        feed_date: "2026-03-10",
        rows_received: 1,
        rows_written: 1,
        checksum_verified: true,
      },
    }),
  });

  // Should not throw even though delete fails
  const result = await runFmcsaDailyDiffWorkflow(
    {
      feed: FMCSA_AUTHHIST_DAILY_FEED,
      schedule: {
        timestamp: "2026-03-10T15:00:00.000Z",
        scheduleId: "schedule-1",
        timezone: "America/New_York",
      },
    },
    {
      client,
      supabaseClient: storage.client,
      fetchImpl: createDownloadFetch(
        '"DK12345","999999","01","Authority Type","Action Desc","03/01/2026","03/10/2026","Filed","Pending"',
      ),
    },
  );

  assert.equal(result.rows_written, 1);
});

test("workflow throws when confirmation has checksum_verified=false", async () => {
  const storage = createMockStorageClient();

  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createManifestCapturingFetch({
      requests: [],
      confirmationResponse: {
        feed_name: "AuthHist",
        table_name: "operating_authority_histories",
        feed_date: "2026-03-10",
        rows_received: 1,
        rows_written: 1,
        checksum_verified: false, // bad
      },
    }),
  });

  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      {
        feed: FMCSA_AUTHHIST_DAILY_FEED,
        schedule: {
          timestamp: "2026-03-10T15:00:00.000Z",
          scheduleId: "schedule-1",
          timezone: "America/New_York",
        },
      },
      {
        client,
        supabaseClient: storage.client,
        fetchImpl: createDownloadFetch(
          '"DK12345","999999","01","Authority Type","Action Desc","03/01/2026","03/10/2026","Filed","Pending"',
        ),
      },
    ),
    (error: Error) => {
      assert.ok(error.message.includes("confirmation failed") || error.name === "PersistenceConfirmationError");
      return true;
    },
  );
});

test("workflow throws when artifact upload fails", async () => {
  const storage = createMockStorageClient({ uploadError: new Error("Bucket full") });

  const client = createInternalApiClient({
    authContext: { orgId: "system" },
    apiUrl: "https://example.com",
    internalApiKey: "secret",
    fetchImpl: createManifestCapturingFetch({
      requests: [],
      confirmationResponse: {},
    }),
  });

  await assert.rejects(
    runFmcsaDailyDiffWorkflow(
      {
        feed: FMCSA_AUTHHIST_DAILY_FEED,
        schedule: {
          timestamp: "2026-03-10T15:00:00.000Z",
          scheduleId: "schedule-1",
          timezone: "America/New_York",
        },
      },
      {
        client,
        supabaseClient: storage.client,
        fetchImpl: createDownloadFetch(
          '"DK12345","999999","01","Authority Type","Action Desc","03/01/2026","03/10/2026","Filed","Pending"',
        ),
      },
    ),
    (error: Error) => {
      assert.ok(error.message.includes("Bucket full"));
      return true;
    },
  );
});
