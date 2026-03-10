import { logger } from "@trigger.dev/sdk/v3";

type FetchLike = typeof fetch;

export type SleepFn = (delayMs: number) => Promise<void>;

type ParallelRequestPhase = "config" | "create" | "status" | "result" | "validation";

interface ParallelCreateResponse {
  run_id: string;
  status: string;
}

interface ParallelStatusResponse {
  status: string;
}

export interface ParallelDeepResearchParams<TExtracted> {
  prompt: string;
  processor?: string | null;
  operationId: string;
  providerAction: string;
  apiKey?: string;
  baseUrl?: string;
  pollingScheduleMs?: readonly number[];
  maxWaitMs?: number;
  createTimeoutMs?: number;
  statusTimeoutMs?: number;
  resultTimeoutMs?: number;
  fetchImpl?: FetchLike;
  sleep?: SleepFn;
  extractOutput: (result: Record<string, unknown>) => TExtracted;
}

export interface ParallelDeepResearchSuccess<TExtracted> {
  parallelRunId: string;
  processor: string;
  pollCount: number;
  elapsedMs: number;
  terminalStatus: string;
  rawResult: Record<string, unknown>;
  extractedOutput: TExtracted;
}

export const DEFAULT_PARALLEL_POLLING_SCHEDULE_MS = [5_000, 10_000, 15_000, 30_000, 60_000] as const;

export class ParallelDeepResearchError extends Error {
  readonly phase: ParallelRequestPhase;
  readonly operationId: string;
  readonly providerAction: string;
  readonly parallelRunId: string | null;
  readonly statusCode: number | null;
  readonly responseBody: unknown;
  readonly pollCount: number;
  readonly elapsedMs: number;
  readonly terminalStatus: string | null;

  constructor(params: {
    message: string;
    phase: ParallelRequestPhase;
    operationId: string;
    providerAction: string;
    parallelRunId?: string | null;
    statusCode?: number | null;
    responseBody?: unknown;
    pollCount?: number;
    elapsedMs?: number;
    terminalStatus?: string | null;
  }) {
    super(params.message);
    this.name = "ParallelDeepResearchError";
    this.phase = params.phase;
    this.operationId = params.operationId;
    this.providerAction = params.providerAction;
    this.parallelRunId = params.parallelRunId ?? null;
    this.statusCode = params.statusCode ?? null;
    this.responseBody = params.responseBody;
    this.pollCount = params.pollCount ?? 0;
    this.elapsedMs = params.elapsedMs ?? 0;
    this.terminalStatus = params.terminalStatus ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.trim().replace(/\/+$/, "");
}

function resolveParallelApiKey(
  apiKey: string | undefined,
  operationId: string,
  providerAction: string,
): string {
  const resolved = apiKey?.trim() || process.env.PARALLEL_API_KEY?.trim();
  if (!resolved) {
    throw new ParallelDeepResearchError({
      message: "Missing required environment variable: PARALLEL_API_KEY",
      phase: "config",
      operationId,
      providerAction,
    });
  }
  return resolved;
}

function resolveProcessor(processor?: string | null): string {
  return processor?.trim() || "pro";
}

function resolvePollingSchedule(schedule?: readonly number[]): number[] {
  const resolved = (schedule ?? DEFAULT_PARALLEL_POLLING_SCHEDULE_MS)
    .map((value) => Math.trunc(value))
    .filter((value) => Number.isFinite(value) && value > 0);

  if (resolved.length === 0) {
    throw new Error("pollingScheduleMs must contain at least one positive interval");
  }

  return resolved;
}

function getPollingDelayMs(pollIndex: number, schedule: readonly number[]): number {
  const boundedIndex = Math.min(Math.max(pollIndex, 0), schedule.length - 1);
  return schedule[boundedIndex] as number;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const responseText = await response.text();
  if (!responseText) {
    return null;
  }

  try {
    return JSON.parse(responseText) as unknown;
  } catch {
    return responseText;
  }
}

async function fetchParallelJson(params: {
  url: string;
  method: "GET" | "POST";
  apiKey: string;
  body?: unknown;
  timeoutMs: number;
  fetchImpl: FetchLike;
  phase: ParallelRequestPhase;
  operationId: string;
  providerAction: string;
  parallelRunId?: string | null;
  pollCount?: number;
  elapsedMs?: number;
  terminalStatus?: string | null;
}): Promise<unknown> {
  let response: Response;

  try {
    response = await params.fetchImpl(params.url, {
      method: params.method,
      headers: {
        "x-api-key": params.apiKey,
        ...(params.method === "POST" ? { "Content-Type": "application/json" } : {}),
      },
      body: params.body === undefined ? undefined : JSON.stringify(params.body),
      signal: AbortSignal.timeout(params.timeoutMs),
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : String(error);
    throw new ParallelDeepResearchError({
      message: `Parallel ${params.phase} request failed: ${message}`,
      phase: params.phase,
      operationId: params.operationId,
      providerAction: params.providerAction,
      parallelRunId: params.parallelRunId,
      pollCount: params.pollCount,
      elapsedMs: params.elapsedMs,
      terminalStatus: params.terminalStatus,
    });
  }

  const responseBody = await parseResponseBody(response);
  if (!response.ok) {
    throw new ParallelDeepResearchError({
      message: `Parallel ${params.phase} request failed (${response.status})`,
      phase: params.phase,
      operationId: params.operationId,
      providerAction: params.providerAction,
      parallelRunId: params.parallelRunId,
      statusCode: response.status,
      responseBody,
      pollCount: params.pollCount,
      elapsedMs: params.elapsedMs,
      terminalStatus: params.terminalStatus,
    });
  }

  return responseBody;
}

function parseCreateResponse(params: {
  payload: unknown;
  operationId: string;
  providerAction: string;
}): ParallelCreateResponse {
  if (!isRecord(params.payload) || typeof params.payload.run_id !== "string" || typeof params.payload.status !== "string") {
    throw new ParallelDeepResearchError({
      message: "Parallel create response missing run_id or status",
      phase: "validation",
      operationId: params.operationId,
      providerAction: params.providerAction,
      responseBody: params.payload,
    });
  }

  return {
    run_id: params.payload.run_id,
    status: params.payload.status,
  };
}

function parseStatusResponse(params: {
  payload: unknown;
  operationId: string;
  providerAction: string;
  parallelRunId: string;
  pollCount: number;
  elapsedMs: number;
}): ParallelStatusResponse {
  if (!isRecord(params.payload) || typeof params.payload.status !== "string") {
    throw new ParallelDeepResearchError({
      message: "Parallel status response missing status",
      phase: "validation",
      operationId: params.operationId,
      providerAction: params.providerAction,
      parallelRunId: params.parallelRunId,
      responseBody: params.payload,
      pollCount: params.pollCount,
      elapsedMs: params.elapsedMs,
    });
  }

  return {
    status: params.payload.status,
  };
}

async function defaultSleep(delayMs: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, delayMs));
}

export async function runParallelDeepResearch<TExtracted>(
  params: ParallelDeepResearchParams<TExtracted>,
): Promise<ParallelDeepResearchSuccess<TExtracted>> {
  const operationId = params.operationId;
  const providerAction = params.providerAction;
  const apiKey = resolveParallelApiKey(params.apiKey, operationId, providerAction);
  const processor = resolveProcessor(params.processor);
  const baseUrl = normalizeBaseUrl(params.baseUrl ?? "https://api.parallel.ai");
  const pollingScheduleMs = resolvePollingSchedule(params.pollingScheduleMs);
  const maxWaitMs = params.maxWaitMs ?? 35 * 60_000;
  const createTimeoutMs = params.createTimeoutMs ?? 30_000;
  const statusTimeoutMs = params.statusTimeoutMs ?? 30_000;
  const resultTimeoutMs = params.resultTimeoutMs ?? 30_000;
  const fetchImpl = params.fetchImpl ?? fetch;
  const sleep = params.sleep ?? defaultSleep;

  const createPayload = await fetchParallelJson({
    url: `${baseUrl}/v1/tasks/runs`,
    method: "POST",
    apiKey,
    body: {
      input: params.prompt,
      processor,
    },
    timeoutMs: createTimeoutMs,
    fetchImpl,
    phase: "create",
    operationId,
    providerAction,
  });

  const createResponse = parseCreateResponse({
    payload: createPayload,
    operationId,
    providerAction,
  });

  const parallelRunId = createResponse.run_id;
  let terminalStatus = createResponse.status;
  let pollCount = 0;
  let elapsedMs = 0;

  logger.info("parallel deep research task created", {
    operation_id: operationId,
    provider_action: providerAction,
    parallel_run_id: parallelRunId,
    processor,
    initial_status: terminalStatus,
  });

  while (terminalStatus !== "completed" && terminalStatus !== "failed") {
    const nextDelayMs = getPollingDelayMs(pollCount, pollingScheduleMs);
    if (elapsedMs + nextDelayMs > maxWaitMs) {
      throw new ParallelDeepResearchError({
        message: `Parallel task timed out after ${elapsedMs}ms`,
        phase: "status",
        operationId,
        providerAction,
        parallelRunId,
        pollCount,
        elapsedMs,
        terminalStatus,
      });
    }

    await sleep(nextDelayMs);
    elapsedMs += nextDelayMs;

    const statusPayload = await fetchParallelJson({
      url: `${baseUrl}/v1/tasks/runs/${parallelRunId}`,
      method: "GET",
      apiKey,
      timeoutMs: statusTimeoutMs,
      fetchImpl,
      phase: "status",
      operationId,
      providerAction,
      parallelRunId,
      pollCount: pollCount + 1,
      elapsedMs,
      terminalStatus,
    });

    const statusResponse = parseStatusResponse({
      payload: statusPayload,
      operationId,
      providerAction,
      parallelRunId,
      pollCount: pollCount + 1,
      elapsedMs,
    });

    pollCount += 1;
    terminalStatus = statusResponse.status;

    logger.info("parallel deep research poll", {
      operation_id: operationId,
      provider_action: providerAction,
      parallel_run_id: parallelRunId,
      poll_count: pollCount,
      elapsed_ms: elapsedMs,
      task_status: terminalStatus,
    });
  }

  if (terminalStatus !== "completed") {
    throw new ParallelDeepResearchError({
      message: `Parallel task ended in non-completed terminal status: ${terminalStatus}`,
      phase: "status",
      operationId,
      providerAction,
      parallelRunId,
      pollCount,
      elapsedMs,
      terminalStatus,
    });
  }

  const resultPayload = await fetchParallelJson({
    url: `${baseUrl}/v1/tasks/runs/${parallelRunId}/result`,
    method: "GET",
    apiKey,
    timeoutMs: resultTimeoutMs,
    fetchImpl,
    phase: "result",
    operationId,
    providerAction,
    parallelRunId,
    pollCount,
    elapsedMs,
    terminalStatus,
  });

  if (!isRecord(resultPayload)) {
    throw new ParallelDeepResearchError({
      message: "Parallel result payload must be an object",
      phase: "validation",
      operationId,
      providerAction,
      parallelRunId,
      responseBody: resultPayload,
      pollCount,
      elapsedMs,
      terminalStatus,
    });
  }

  let extractedOutput: TExtracted;
  try {
    extractedOutput = params.extractOutput(resultPayload);
  } catch (error) {
    throw new ParallelDeepResearchError({
      message:
        error instanceof Error
          ? `Parallel result extraction failed: ${error.message}`
          : `Parallel result extraction failed: ${String(error)}`,
      phase: "validation",
      operationId,
      providerAction,
      parallelRunId,
      responseBody: resultPayload,
      pollCount,
      elapsedMs,
      terminalStatus,
    });
  }

  return {
    parallelRunId,
    processor,
    pollCount,
    elapsedMs,
    terminalStatus,
    rawResult: resultPayload,
    extractedOutput,
  };
}
