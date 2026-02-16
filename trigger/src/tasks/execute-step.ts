import { logger, task } from "@trigger.dev/sdk/v3";

type AuthType = "bearer_token" | "api_key_header" | "none" | null;

interface StepConfig {
  url: string;
  method: string;
  auth_type: AuthType;
  auth_config: Record<string, unknown>;
  payload_template: Record<string, unknown> | unknown[] | null;
  response_mapping: Record<string, unknown> | unknown[] | string | null;
  timeout_ms: number;
  retry_config: {
    max_attempts?: number;
    backoff_factor?: number;
  } | null;
}

interface ExecuteStepPayload {
  pipeline_run_id: string;
  step_result_id: string;
  step_config: StepConfig;
  input_data: Record<string, unknown> | unknown[];
  metadata: {
    org_id: string;
    company_id: string;
    step_slug: string;
    step_position: number;
  };
}

function getValueByPath(root: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, segment) => {
    if (acc === null || typeof acc !== "object") return undefined;
    const record = acc as Record<string, unknown>;
    return record[segment];
  }, root);
}

function applyTemplate(template: unknown, inputData: unknown): unknown {
  if (typeof template === "string") {
    const match = template.match(/^\{\{input\.([a-zA-Z0-9_.-]+)\}\}$/);
    if (!match) return template;
    return getValueByPath(inputData, match[1]);
  }

  if (Array.isArray(template)) {
    return template.map((item) => applyTemplate(item, inputData));
  }

  if (template && typeof template === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(template as Record<string, unknown>)) {
      output[key] = applyTemplate(value, inputData);
    }
    return output;
  }

  return template;
}

function mapResponseBody(responseBody: unknown, responseMapping: StepConfig["response_mapping"]): unknown {
  if (!responseMapping) return responseBody;

  if (typeof responseMapping === "string") {
    return getValueByPath(responseBody, responseMapping);
  }

  if (Array.isArray(responseMapping)) {
    return responseMapping.map((item) => mapResponseBody(responseBody, item as any));
  }

  if (typeof responseMapping === "object") {
    const mapping = responseMapping as Record<string, unknown>;
    if (typeof mapping.path === "string") {
      return getValueByPath(responseBody, mapping.path);
    }
    const output: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(mapping)) {
      if (typeof value === "string") {
        output[key] = getValueByPath(responseBody, value);
      } else {
        output[key] = value;
      }
    }
    return output;
  }

  return responseBody;
}

function resolveAuthHeaders(stepConfig: StepConfig): Record<string, string> {
  const headers: Record<string, string> = {};
  const authType = stepConfig.auth_type;
  const authConfig = stepConfig.auth_config || {};

  if (!authType || authType === "none") {
    return headers;
  }

  if (authType === "bearer_token") {
    const tokenEnvVar = authConfig["token_env_var"];
    if (typeof tokenEnvVar !== "string" || tokenEnvVar.length === 0) {
      throw new Error("auth_config.token_env_var is required for bearer_token auth");
    }
    const tokenValue = process.env[tokenEnvVar];
    if (!tokenValue) {
      throw new Error(`Missing environment variable for bearer token: ${tokenEnvVar}`);
    }
    headers["Authorization"] = `Bearer ${tokenValue}`;
    return headers;
  }

  if (authType === "api_key_header") {
    const headerName = authConfig["header_name"];
    const keyEnvVar = authConfig["key_env_var"];
    if (typeof headerName !== "string" || typeof keyEnvVar !== "string") {
      throw new Error("auth_config.header_name and auth_config.key_env_var are required for api_key_header auth");
    }
    const apiKey = process.env[keyEnvVar];
    if (!apiKey) {
      throw new Error(`Missing environment variable for API key: ${keyEnvVar}`);
    }
    headers[headerName] = apiKey;
    return headers;
  }

  throw new Error(`Unsupported auth_type: ${authType}`);
}

export const executeStep = task({
  id: "execute-step",
  retry: {
    maxAttempts: 3,
    factor: 2,
    minTimeoutInMs: 1000,
    maxTimeoutInMs: 30000,
    randomize: true,
  },
  run: async (payload: ExecuteStepPayload) => {
    const { pipeline_run_id, step_result_id, step_config, input_data, metadata } = payload;
    const startedAt = Date.now();

    logger.info("execute-step start", {
      pipeline_run_id,
      step_result_id,
      step_slug: metadata.step_slug,
      step_position: metadata.step_position,
      tags: [
        `step:${metadata.step_slug}`,
        `org:${metadata.org_id}`,
        `pipeline:${pipeline_run_id}`,
      ],
    });

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...resolveAuthHeaders(step_config),
    };

    const requestBody =
      step_config.payload_template === null
        ? input_data
        : applyTemplate(step_config.payload_template, input_data);

    const timeoutMs = step_config.timeout_ms ?? 30000;
    const method = (step_config.method || "POST").toUpperCase();

    const response = await fetch(step_config.url, {
      method,
      headers,
      body: ["GET", "HEAD"].includes(method) ? undefined : JSON.stringify(requestBody),
      signal: AbortSignal.timeout(timeoutMs),
    });

    let responseBody: unknown = null;
    const responseText = await response.text();
    try {
      responseBody = responseText ? JSON.parse(responseText) : null;
    } catch {
      responseBody = responseText;
    }

    if (!response.ok) {
      throw new Error(
        `Step request failed (${response.status}): ${
          typeof responseBody === "string" ? responseBody : JSON.stringify(responseBody)
        }`,
      );
    }

    const outputData = mapResponseBody(responseBody, step_config.response_mapping);
    const durationMs = Date.now() - startedAt;

    return {
      output_data: outputData,
      status_code: response.status,
      duration_ms: durationMs,
    };
  },
});
