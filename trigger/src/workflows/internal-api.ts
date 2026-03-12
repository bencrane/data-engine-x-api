import { gzipSync } from "node:zlib";

export interface InternalAuthContext {
  orgId: string;
  companyId?: string | null;
}

export interface InternalApiConfig {
  apiUrl: string;
  internalApiKey: string;
  defaultTimeoutMs: number;
}

export interface InternalApiClientOptions {
  authContext: InternalAuthContext;
  apiUrl?: string;
  internalApiKey?: string;
  defaultTimeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface InternalPostOptions<TResponse> {
  timeoutMs?: number;
  validate?: (data: TResponse) => boolean;
  validationErrorMessage?: string;
}

interface DataEnvelope<TData> {
  data?: TData;
  error?: string;
}

type FetchLike = typeof fetch;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeApiUrl(apiUrl: string): string {
  return apiUrl.trim().replace(/\/+$/, "");
}

function requireEnv(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
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

export class InternalApiError extends Error {
  readonly path: string;
  readonly statusCode: number | null;
  readonly responseBody: unknown;

  constructor(params: {
    message: string;
    path: string;
    statusCode?: number | null;
    responseBody?: unknown;
  }) {
    super(params.message);
    this.name = "InternalApiError";
    this.path = params.path;
    this.statusCode = params.statusCode ?? null;
    this.responseBody = params.responseBody;
  }
}

export class InternalApiTimeoutError extends InternalApiError {
  constructor(params: { path: string; timeoutMs: number }) {
    super({
      message: `Internal API request timed out after ${params.timeoutMs}ms: ${params.path}`,
      path: params.path,
      statusCode: null,
    });
    this.name = "InternalApiTimeoutError";
  }
}

export function resolveInternalApiConfig(
  overrides: Partial<Pick<InternalApiConfig, "apiUrl" | "internalApiKey" | "defaultTimeoutMs">> = {},
): InternalApiConfig {
  const apiUrl =
    overrides.apiUrl ??
    process.env.DATA_ENGINE_API_URL ??
    process.env.API_URL ??
    "http://localhost:8000";

  const internalApiKey =
    overrides.internalApiKey ??
    process.env.DATA_ENGINE_INTERNAL_API_KEY ??
    process.env.INTERNAL_API_KEY ??
    requireEnv("DATA_ENGINE_INTERNAL_API_KEY");

  return {
    apiUrl: normalizeApiUrl(apiUrl),
    internalApiKey,
    defaultTimeoutMs: overrides.defaultTimeoutMs ?? 120_000,
  };
}

export class InternalApiClient {
  private readonly config: InternalApiConfig;
  private readonly authContext: InternalAuthContext;
  private readonly fetchImpl: FetchLike;

  constructor(options: InternalApiClientOptions) {
    this.config = resolveInternalApiConfig({
      apiUrl: options.apiUrl,
      internalApiKey: options.internalApiKey,
      defaultTimeoutMs: options.defaultTimeoutMs,
    });
    this.authContext = options.authContext;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async post<TResponse>(
    path: string,
    payload: unknown,
    options: InternalPostOptions<TResponse> = {},
  ): Promise<TResponse> {
    const timeoutMs = options.timeoutMs ?? this.config.defaultTimeoutMs;

    let response: Response;

    try {
      const jsonBody = JSON.stringify(payload);
      const compressedBody = gzipSync(jsonBody);

      response = await this.fetchImpl(`${this.config.apiUrl}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Encoding": "gzip",
          Authorization: `Bearer ${this.config.internalApiKey}`,
          "x-internal-org-id": this.authContext.orgId,
          ...(this.authContext.companyId
            ? { "x-internal-company-id": this.authContext.companyId }
            : {}),
        },
        body: compressedBody,
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      if (error instanceof Error && (error.name === "TimeoutError" || error.name === "AbortError")) {
        throw new InternalApiTimeoutError({ path, timeoutMs });
      }

      throw new InternalApiError({
        message:
          error instanceof Error
            ? `Internal API request failed: ${error.message}`
            : `Internal API request failed: ${String(error)}`,
        path,
        statusCode: null,
      });
    }

    const responseBody = await parseResponseBody(response);
    const envelope = isRecord(responseBody) ? (responseBody as DataEnvelope<TResponse>) : null;

    if (!response.ok) {
      throw new InternalApiError({
        message:
          (envelope?.error && String(envelope.error)) ||
          `Internal API request failed (${response.status}): ${path}`,
        path,
        statusCode: response.status,
        responseBody,
      });
    }

    if (!envelope || envelope.data === undefined) {
      throw new InternalApiError({
        message: `Internal API response missing data envelope: ${path}`,
        path,
        statusCode: response.status,
        responseBody,
      });
    }

    if (options.validate && !options.validate(envelope.data)) {
      throw new InternalApiError({
        message:
          options.validationErrorMessage ||
          `Internal API response failed validation: ${path}`,
        path,
        statusCode: response.status,
        responseBody,
      });
    }

    return envelope.data;
  }
}

export function createInternalApiClient(options: InternalApiClientOptions): InternalApiClient {
  return new InternalApiClient(options);
}
