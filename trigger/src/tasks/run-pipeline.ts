import { logger, task } from "@trigger.dev/sdk/v3";
import { executeStep } from "./execute-step";

interface RunPipelinePayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  api_url?: string;
  internal_api_key?: string;
}

interface InternalPipelineRun {
  id: string;
  org_id: string;
  company_id: string;
  submission_id: string;
  blueprint_snapshot: {
    blueprint: Record<string, unknown>;
    steps: Array<{
      id: string;
      step_id: string;
      position: number;
      config: Record<string, unknown>;
      steps: Record<string, unknown>;
    }>;
  };
  step_results: Array<{
    id: string;
    step_id: string;
    step_position: number;
    status: string;
  }>;
  submissions: {
    id: string;
    input_payload: Record<string, unknown> | unknown[];
  };
}

interface InternalConfig {
  apiUrl: string;
  internalApiKey: string;
}

function resolveInternalConfig(payload: RunPipelinePayload): InternalConfig {
  const apiUrl = payload.api_url || process.env.DATA_ENGINE_API_URL;
  const internalApiKey = payload.internal_api_key || process.env.DATA_ENGINE_INTERNAL_API_KEY;

  if (!apiUrl) throw new Error("DATA_ENGINE_API_URL is not configured");
  if (!internalApiKey) throw new Error("DATA_ENGINE_INTERNAL_API_KEY is not configured");

  return { apiUrl, internalApiKey };
}

async function internalPost<TResponse>(
  internalConfig: InternalConfig,
  path: string,
  payload: Record<string, unknown>,
): Promise<TResponse> {
  const response = await fetch(`${internalConfig.apiUrl}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${internalConfig.internalApiKey}`,
    },
    body: JSON.stringify(payload),
  });

  const body = (await response.json()) as { data?: TResponse; error?: string };
  if (!response.ok) {
    throw new Error(body.error || `Internal API failed: ${path}`);
  }
  if (body.data === undefined) {
    throw new Error(`Internal API missing data envelope: ${path}`);
  }
  return body.data;
}

function buildStepConfig(
  stepSnapshot: {
    config: Record<string, unknown>;
    steps: Record<string, unknown>;
  },
): {
  url: string;
  method: string;
  auth_type: "bearer_token" | "api_key_header" | "none" | null;
  auth_config: Record<string, unknown>;
  payload_template: Record<string, unknown> | unknown[] | null;
  response_mapping: Record<string, unknown> | unknown[] | string | null;
  timeout_ms: number;
  retry_config: Record<string, unknown>;
} {
  const base = stepSnapshot.steps;
  const override = stepSnapshot.config || {};
  const rawAuthType =
    (override.auth_type as string | null | undefined) ??
    ((base.auth_type as string | null | undefined) ?? null);
  const authType =
    rawAuthType === "bearer_token" ||
    rawAuthType === "api_key_header" ||
    rawAuthType === "none" ||
    rawAuthType === null
      ? rawAuthType
      : null;

  return {
    url: (override.url as string) ?? (base.url as string),
    method: (override.method as string) ?? ((base.method as string) || "POST"),
    auth_type: authType,
    auth_config:
      (override.auth_config as Record<string, unknown>) ??
      ((base.auth_config as Record<string, unknown>) || {}),
    payload_template:
      override.payload_template !== undefined
        ? (override.payload_template as Record<string, unknown> | unknown[] | null)
        : ((base.payload_template as Record<string, unknown> | unknown[] | null) ?? null),
    response_mapping:
      override.response_mapping !== undefined
        ? (override.response_mapping as Record<string, unknown> | unknown[] | string | null)
        : ((base.response_mapping as Record<string, unknown> | unknown[] | string | null) ?? null),
    timeout_ms: (override.timeout_ms as number) ?? ((base.timeout_ms as number) || 30000),
    retry_config:
      (override.retry_config as Record<string, unknown>) ??
      ((base.retry_config as Record<string, unknown>) || { max_attempts: 3, backoff_factor: 2 }),
  };
}

export const runPipeline = task({
  id: "run-pipeline",
  retry: {
    maxAttempts: 1,
  },
  run: async (payload: RunPipelinePayload) => {
    const { pipeline_run_id, org_id, company_id } = payload;
    const internalConfig = resolveInternalConfig(payload);

    logger.info("run-pipeline start", { pipeline_run_id, org_id, company_id });

    const run = await internalPost<InternalPipelineRun>(
      internalConfig,
      "/api/internal/pipeline-runs/get",
      { pipeline_run_id },
    );

    await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
      pipeline_run_id,
      status: "running",
    });
    await internalPost(internalConfig, "/api/internal/submissions/update-status", {
      submission_id: run.submission_id,
      status: "running",
    });

    const orderedSteps = [...run.blueprint_snapshot.steps].sort(
      (a, b) => a.position - b.position,
    );

    let currentInput: Record<string, unknown> | unknown[] = run.submissions.input_payload || {};

    for (const stepSnapshot of orderedSteps) {
      const stepResult = run.step_results.find(
        (sr) => sr.step_position === stepSnapshot.position,
      );

      if (!stepResult) {
        throw new Error(`Missing step_result for position ${stepSnapshot.position}`);
      }

      const stepMeta = stepSnapshot.steps;
      const stepSlug = (stepMeta.slug as string) || `step-${stepSnapshot.position}`;
      const stepConfig = buildStepConfig(stepSnapshot);

      await internalPost(internalConfig, "/api/internal/step-results/update", {
        step_result_id: stepResult.id,
        status: "running",
      });

      try {
        const stepRun = await executeStep.triggerAndWait({
          pipeline_run_id,
          step_result_id: stepResult.id,
          step_config: stepConfig,
          input_data: currentInput,
          metadata: {
            org_id,
            company_id,
            step_slug: stepSlug,
            step_position: stepSnapshot.position,
          },
        });

        if (!stepRun.ok) {
          throw new Error(String(stepRun.error || "execute-step failed"));
        }

        currentInput = (stepRun.output.output_data ??
          stepRun.output) as Record<string, unknown> | unknown[];

        await internalPost(internalConfig, "/api/internal/step-results/update", {
          step_result_id: stepResult.id,
          status: "succeeded",
          output_payload: stepRun.output.output_data ?? stepRun.output,
          duration_ms: stepRun.output.duration_ms,
          task_run_id: stepRun.id,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        await internalPost(internalConfig, "/api/internal/step-results/update", {
          step_result_id: stepResult.id,
          status: "failed",
          error_message: message,
          error_details: { error: message },
        });

        await internalPost(internalConfig, "/api/internal/step-results/mark-remaining-skipped", {
          pipeline_run_id,
          from_step_position: stepSnapshot.position,
        });

        await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
          pipeline_run_id,
          status: "failed",
          error_message: message,
          error_details: { error: message },
        });

        await internalPost(internalConfig, "/api/internal/submissions/update-status", {
          submission_id: run.submission_id,
          status: "failed",
        });

        return {
          pipeline_run_id,
          status: "failed",
          failed_step_position: stepSnapshot.position,
          error: message,
        };
      }
    }

    await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
      pipeline_run_id,
      status: "succeeded",
    });
    await internalPost(internalConfig, "/api/internal/submissions/update-status", {
      submission_id: run.submission_id,
      status: "completed",
    });

    return {
      pipeline_run_id,
      status: "succeeded",
    };
  },
});
