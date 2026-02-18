import { logger, task } from "@trigger.dev/sdk/v3";
import { evaluateCondition } from "../utils/evaluate-condition.js";

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
      position: number;
      operation_id?: string | null;
      step_config?: Record<string, unknown> | null;
      condition?: Record<string, unknown> | null;
      fan_out?: boolean;
      is_enabled?: boolean;
    }>;
    entity?: {
      entity_type?: "person" | "company";
      input?: Record<string, unknown>;
      index?: number;
    };
    fan_out?: {
      parent_pipeline_run_id?: string;
      start_from_position?: number;
    };
  };
  step_results: Array<{
    id: string;
    step_position: number;
    status: string;
  }>;
  submissions: {
    id: string;
    input_payload: Record<string, unknown> | unknown[];
  };
}

interface FanOutChildRunsResponse {
  parent_pipeline_run_id: string;
  child_runs: Array<{
    pipeline_run_id: string;
    pipeline_run_status: string;
    trigger_run_id?: string | null;
    entity_type?: string;
    entity_input?: Record<string, unknown>;
  }>;
  child_run_ids: string[];
  skipped_duplicates_count?: number;
  skipped_duplicate_identifiers?: string[];
}

interface ExecuteResponseEnvelope {
  data?: {
    run_id: string;
    operation_id: string;
    status: string;
    output?: Record<string, unknown> | null;
    provider_attempts?: Array<Record<string, unknown>>;
    missing_inputs?: string[];
  };
  error?: string;
}

interface FreshnessCheckResponse {
  fresh: boolean;
  entity_id?: string | null;
  last_enriched_at?: string | null;
  age_hours?: number | null;
  canonical_payload?: Record<string, unknown> | null;
}

interface InternalEnvelope<TData> {
  data?: TData;
  error?: string;
}

interface InternalConfig {
  apiUrl: string;
  internalApiKey: string;
}

interface InternalStepResult {
  id: string;
  step_position: number;
  duration_ms?: number | null;
}

interface SkipIfFreshConfig {
  maxAgeHours: number;
  identityFields: string[];
}

function getExecutionStartPosition(run: InternalPipelineRun): number {
  const fanOutStart = run.blueprint_snapshot.fan_out?.start_from_position;
  if (typeof fanOutStart === "number" && Number.isInteger(fanOutStart) && fanOutStart > 0) {
    return fanOutStart;
  }

  if (run.step_results.length > 0) {
    return run.step_results.reduce((min, stepResult) => Math.min(min, stepResult.step_position), Number.MAX_SAFE_INTEGER);
  }

  return 1;
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
  const body = (await response.json()) as InternalEnvelope<TResponse>;
  if (!response.ok) throw new Error(body.error || `Internal API failed: ${path}`);
  if (body.data === undefined) throw new Error(`Internal API missing data envelope: ${path}`);
  return body.data;
}

async function callExecuteV1(
  internalConfig: InternalConfig,
  params: {
    orgId: string;
    companyId: string;
    operationId: string;
    entityType: "person" | "company";
    input: Record<string, unknown>;
    options: Record<string, unknown> | null;
  },
): Promise<NonNullable<ExecuteResponseEnvelope["data"]>> {
  const { orgId, companyId, operationId, entityType, input, options } = params;
  const response = await fetch(`${internalConfig.apiUrl}/api/v1/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${internalConfig.internalApiKey}`,
      "x-internal-org-id": orgId,
      "x-internal-company-id": companyId,
    },
    body: JSON.stringify({
      operation_id: operationId,
      entity_type: entityType,
      input,
      options: options ?? undefined,
    }),
  });
  const body = (await response.json()) as ExecuteResponseEnvelope;
  if (!response.ok) throw new Error(body.error || `Execute v1 request failed (${response.status})`);
  if (!body.data) throw new Error("Execute v1 response missing data envelope");
  return body.data as NonNullable<ExecuteResponseEnvelope["data"]>;
}

async function callEntityStateFreshnessCheck(
  internalConfig: InternalConfig,
  params: {
    orgId: string;
    companyId: string;
    entityType: "person" | "company";
    identifiers: Record<string, unknown>;
    maxAgeHours: number;
  },
): Promise<FreshnessCheckResponse> {
  const response = await fetch(`${internalConfig.apiUrl}/api/internal/entity-state/check-freshness`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${internalConfig.internalApiKey}`,
      "x-internal-org-id": params.orgId,
      "x-internal-company-id": params.companyId,
    },
    body: JSON.stringify({
      entity_type: params.entityType,
      identifiers: params.identifiers,
      max_age_hours: params.maxAgeHours,
    }),
  });
  const body = (await response.json()) as InternalEnvelope<FreshnessCheckResponse>;
  if (!response.ok) throw new Error(body.error || "Freshness check request failed");
  if (!body.data) throw new Error("Freshness check response missing data envelope");
  return body.data;
}

function entityTypeFromOperationId(operationId: string): "person" | "company" {
  if (operationId.startsWith("person.")) return "person";
  return "company";
}

function mergeContext(
  current: Record<string, unknown>,
  output: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  if (!output) return current;
  return { ...current, ...output };
}

function extractFanOutResults(output: Record<string, unknown> | null | undefined): Array<Record<string, unknown>> {
  if (!output) return [];
  const value = output["results"];
  if (!Array.isArray(value)) return [];
  return value.filter((item) => typeof item === "object" && item !== null) as Array<Record<string, unknown>>;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getStepCondition(
  stepSnapshot: InternalPipelineRun["blueprint_snapshot"]["steps"][number],
): Record<string, unknown> | null {
  if (isObject(stepSnapshot.step_config) && "condition" in stepSnapshot.step_config) {
    const fromConfig = stepSnapshot.step_config.condition;
    if (isObject(fromConfig)) return fromConfig;
    if (fromConfig === null) return null;
  }
  if (isObject(stepSnapshot.condition)) {
    return stepSnapshot.condition;
  }
  return null;
}

function getSkipIfFreshConfig(
  stepSnapshot: InternalPipelineRun["blueprint_snapshot"]["steps"][number],
): SkipIfFreshConfig | null {
  const rawConfig = isObject(stepSnapshot.step_config) ? stepSnapshot.step_config.skip_if_fresh : null;
  if (!isObject(rawConfig)) return null;

  const maxAgeRaw = rawConfig.max_age_hours;
  const identityFieldsRaw = rawConfig.identity_fields;

  if (typeof maxAgeRaw !== "number" || !Number.isFinite(maxAgeRaw) || maxAgeRaw <= 0) return null;
  if (!Array.isArray(identityFieldsRaw)) return null;

  const identityFields = identityFieldsRaw
    .filter((field): field is string => typeof field === "string")
    .map((field) => field.trim())
    .filter((field) => field.length > 0);

  if (identityFields.length === 0) return null;
  return { maxAgeHours: maxAgeRaw, identityFields };
}

function extractFreshnessIdentifiers(
  cumulativeContext: Record<string, unknown>,
  identityFields: string[],
): Record<string, unknown> {
  return identityFields.reduce<Record<string, unknown>>((acc, field) => {
    const value = cumulativeContext[field];
    if (value !== undefined && value !== null && value !== "") {
      acc[field] = value;
    }
    return acc;
  }, {});
}

function inferFieldsUpdatedFromOperationResult(
  operationResult: Record<string, unknown> | null | undefined,
): string[] | null {
  if (!isObject(operationResult) || !isObject(operationResult.output)) {
    return null;
  }
  const keys = Object.entries(operationResult.output)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key]) => key)
    .sort();
  return keys.length > 0 ? keys : null;
}

function operationIdForStep(
  step: InternalPipelineRun["blueprint_snapshot"]["steps"][number] | undefined,
): string {
  return step?.operation_id || "unknown.operation";
}

async function emitStepTimelineEvent(
  internalConfig: InternalConfig,
  payload: {
    orgId: string;
    companyId: string;
    submissionId: string;
    pipelineRunId: string;
    entityType: "person" | "company";
    cumulativeContext: Record<string, unknown>;
    stepResultId: string;
    stepPosition: number;
    operationId: string;
    stepStatus: "succeeded" | "failed" | "skipped";
    skipReason?: string | null;
    durationMs?: number | null;
    providerAttempts?: Array<Record<string, unknown>>;
    condition?: Record<string, unknown> | null;
    errorMessage?: string | null;
    errorDetails?: Record<string, unknown> | null;
    operationResult?: Record<string, unknown> | null;
  },
): Promise<void> {
  try {
    await internalPost(internalConfig, "/api/internal/entity-timeline/record-step-event", {
      org_id: payload.orgId,
      company_id: payload.companyId,
      submission_id: payload.submissionId,
      pipeline_run_id: payload.pipelineRunId,
      entity_type: payload.entityType,
      cumulative_context: payload.cumulativeContext,
      step_result_id: payload.stepResultId,
      step_position: payload.stepPosition,
      operation_id: payload.operationId,
      step_status: payload.stepStatus,
      skip_reason: payload.skipReason ?? null,
      duration_ms: payload.durationMs ?? null,
      provider_attempts: payload.providerAttempts ?? [],
      condition: payload.condition ?? null,
      error_message: payload.errorMessage ?? null,
      error_details: payload.errorDetails ?? null,
      operation_result: payload.operationResult ?? null,
      fields_updated: inferFieldsUpdatedFromOperationResult(payload.operationResult),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logger.warn("step timeline emit failed", {
      pipeline_run_id: payload.pipelineRunId,
      step_result_id: payload.stepResultId,
      step_position: payload.stepPosition,
      operation_id: payload.operationId,
      step_status: payload.stepStatus,
      error: message,
    });
  }
}

async function skipStepWithReason(
  internalConfig: InternalConfig,
  stepResultId: string,
  cumulativeContext: Record<string, unknown>,
  skipReason: string,
  metadata: Record<string, unknown>,
): Promise<InternalStepResult> {
  return internalPost<InternalStepResult>(internalConfig, "/api/internal/step-results/update", {
    step_result_id: stepResultId,
    status: "skipped",
    input_payload: cumulativeContext,
    output_payload: {
      skip_reason: skipReason,
      metadata,
    },
  });
}

export const runPipeline = task({
  id: "run-pipeline",
  retry: { maxAttempts: 1 },
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
    await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
      submission_id: run.submission_id,
    });

    const executionStartPosition = getExecutionStartPosition(run);
    const orderedSteps = [...run.blueprint_snapshot.steps]
      .filter((step) => step.is_enabled !== false)
      .filter((step) => step.position >= executionStartPosition)
      .sort((a, b) => a.position - b.position);
    const stepsByPosition = new Map(orderedSteps.map((step) => [step.position, step]));

    const snapshotEntity = run.blueprint_snapshot.entity || {};
    const entityType =
      snapshotEntity.entity_type === "person" || snapshotEntity.entity_type === "company"
        ? snapshotEntity.entity_type
        : "company";
    const submissionInput =
      run.submissions.input_payload &&
      typeof run.submissions.input_payload === "object" &&
      !Array.isArray(run.submissions.input_payload)
        ? (run.submissions.input_payload as Record<string, unknown>)
        : {};
    const initialInput = snapshotEntity.input || submissionInput;
    let cumulativeContext: Record<string, unknown> = { ...initialInput };
    let lastSuccessfulOperationId: string | null = null;
    let shouldShortCircuitRemainingSteps = false;

    for (const stepSnapshot of orderedSteps) {
      if (shouldShortCircuitRemainingSteps) {
        break;
      }

      const stepResult = run.step_results.find((sr) => sr.step_position === stepSnapshot.position);
      if (!stepResult) throw new Error(`Missing step_result for position ${stepSnapshot.position}`);

      const operationId = stepSnapshot.operation_id;
      if (!operationId) {
        const message = `Missing operation_id for blueprint step at position ${stepSnapshot.position}`;
        const failedStep = await internalPost<InternalStepResult>(
          internalConfig,
          "/api/internal/step-results/update",
          {
            step_result_id: stepResult.id,
            status: "failed",
            input_payload: cumulativeContext,
            error_message: message,
            error_details: { error: message },
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType,
          cumulativeContext,
          stepResultId: failedStep.id,
          stepPosition: failedStep.step_position,
          operationId: "unknown.operation",
          stepStatus: "failed",
          durationMs: failedStep.duration_ms,
          errorMessage: message,
          errorDetails: { error: message },
        });
        const skippedRows = await internalPost<Array<InternalStepResult>>(
          internalConfig,
          "/api/internal/step-results/mark-remaining-skipped",
          {
            pipeline_run_id,
            from_step_position: stepSnapshot.position,
          },
        );
        for (const skippedStep of skippedRows) {
          const skippedBlueprintStep = stepsByPosition.get(skippedStep.step_position);
          await emitStepTimelineEvent(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            submissionId: run.submission_id,
            pipelineRunId: pipeline_run_id,
            entityType: entityTypeFromOperationId(operationIdForStep(skippedBlueprintStep)),
            cumulativeContext,
            stepResultId: skippedStep.id,
            stepPosition: skippedStep.step_position,
            operationId: operationIdForStep(skippedBlueprintStep),
            stepStatus: "skipped",
            skipReason: "upstream_step_failed",
            durationMs: skippedStep.duration_ms,
            errorMessage: "Skipped because a prior step failed",
            errorDetails: {
              failed_step_position: stepSnapshot.position,
            },
          });
        }
        await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
          pipeline_run_id,
          status: "failed",
          error_message: message,
          error_details: { error: message },
        });
        await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
          submission_id: run.submission_id,
        });
        return { pipeline_run_id, status: "failed", failed_step_position: stepSnapshot.position, error: message };
      }

      const condition = getStepCondition(stepSnapshot);
      const shouldRun = evaluateCondition(condition, cumulativeContext);
      if (!shouldRun) {
        const skippedStep = await skipStepWithReason(
          internalConfig,
          stepResult.id,
          cumulativeContext,
          "condition_not_met",
          {
            condition,
            step_position: stepSnapshot.position,
            operation_id: operationId,
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType: entityTypeFromOperationId(operationId),
          cumulativeContext,
          stepResultId: skippedStep.id,
          stepPosition: skippedStep.step_position,
          operationId,
          stepStatus: "skipped",
          skipReason: "condition_not_met",
          durationMs: skippedStep.duration_ms,
          condition,
        });

        const fanOutEnabled =
          stepSnapshot.fan_out === true ||
          stepSnapshot.step_config?.fan_out === true;

        if (fanOutEnabled) {
          for (const downstreamStep of orderedSteps) {
            if (downstreamStep.position <= stepSnapshot.position) continue;
            const downstreamStepResult = run.step_results.find(
              (sr) => sr.step_position === downstreamStep.position,
            );
            if (!downstreamStepResult) continue;
            const downstreamSkippedStep = await skipStepWithReason(
              internalConfig,
              downstreamStepResult.id,
              cumulativeContext,
              "parent_step_condition_not_met",
              {
                parent_step_position: stepSnapshot.position,
                parent_operation_id: operationId,
                parent_condition: condition,
              },
            );
            await emitStepTimelineEvent(internalConfig, {
              orgId: org_id,
              companyId: company_id,
              submissionId: run.submission_id,
              pipelineRunId: pipeline_run_id,
              entityType: entityTypeFromOperationId(operationIdForStep(downstreamStep)),
              cumulativeContext,
              stepResultId: downstreamSkippedStep.id,
              stepPosition: downstreamSkippedStep.step_position,
              operationId: operationIdForStep(downstreamStep),
              stepStatus: "skipped",
              skipReason: "parent_step_condition_not_met",
              durationMs: downstreamSkippedStep.duration_ms,
              condition,
              errorDetails: {
                parent_step_position: stepSnapshot.position,
                parent_operation_id: operationId,
              },
            });
          }
          shouldShortCircuitRemainingSteps = true;
        }

        continue;
      }

      const stepEntityType = entityTypeFromOperationId(operationId);
      const skipIfFresh = getSkipIfFreshConfig(stepSnapshot);
      if (skipIfFresh) {
        try {
          const freshness = await callEntityStateFreshnessCheck(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            entityType: stepEntityType,
            identifiers: extractFreshnessIdentifiers(cumulativeContext, skipIfFresh.identityFields),
            maxAgeHours: skipIfFresh.maxAgeHours,
          });

          if (freshness.fresh) {
            cumulativeContext = mergeContext(cumulativeContext, freshness.canonical_payload);
            const freshnessMetadata = {
              entity_id: freshness.entity_id ?? null,
              age_hours: freshness.age_hours ?? null,
              last_enriched_at: freshness.last_enriched_at ?? null,
              max_age_hours: skipIfFresh.maxAgeHours,
              identity_fields: skipIfFresh.identityFields,
            };
            const skippedStep = await skipStepWithReason(
              internalConfig,
              stepResult.id,
              cumulativeContext,
              "entity_state_fresh",
              freshnessMetadata,
            );
            await emitStepTimelineEvent(internalConfig, {
              orgId: org_id,
              companyId: company_id,
              submissionId: run.submission_id,
              pipelineRunId: pipeline_run_id,
              entityType: stepEntityType,
              cumulativeContext,
              stepResultId: skippedStep.id,
              stepPosition: skippedStep.step_position,
              operationId,
              stepStatus: "skipped",
              skipReason: "entity_state_fresh",
              durationMs: skippedStep.duration_ms,
              condition,
              errorDetails: freshnessMetadata,
            });
            continue;
          }
        } catch (error) {
          logger.warn("freshness check failed; continuing with live execution", {
            pipeline_run_id,
            step_position: stepSnapshot.position,
            operation_id: operationId,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }

      await internalPost(internalConfig, "/api/internal/step-results/update", {
        step_result_id: stepResult.id,
        status: "running",
        input_payload: cumulativeContext,
      });

      try {
        const result = await callExecuteV1(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          operationId,
          entityType: stepEntityType,
          input: cumulativeContext,
          options: stepSnapshot.step_config || null,
        });

        cumulativeContext = mergeContext(cumulativeContext, result.output);
        const stepFailed = result.status === "failed";
        if (stepFailed) {
          const message = `Operation failed: ${operationId}`;
          const failedStep = await internalPost<InternalStepResult>(
            internalConfig,
            "/api/internal/step-results/update",
            {
              step_result_id: stepResult.id,
              status: "failed",
              output_payload: {
                operation_result: result,
                cumulative_context: cumulativeContext,
              },
              error_message: message,
              error_details: {
                operation_id: operationId,
                missing_inputs: result.missing_inputs || [],
              },
            },
          );
          await emitStepTimelineEvent(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            submissionId: run.submission_id,
            pipelineRunId: pipeline_run_id,
            entityType: stepEntityType,
            cumulativeContext,
            stepResultId: failedStep.id,
            stepPosition: failedStep.step_position,
            operationId,
            stepStatus: "failed",
            durationMs: failedStep.duration_ms,
            providerAttempts: Array.isArray(result.provider_attempts) ? result.provider_attempts : [],
            errorMessage: message,
            errorDetails: {
              operation_id: operationId,
              missing_inputs: result.missing_inputs || [],
            },
            operationResult: result as unknown as Record<string, unknown>,
          });
          const skippedRows = await internalPost<Array<InternalStepResult>>(
            internalConfig,
            "/api/internal/step-results/mark-remaining-skipped",
            {
              pipeline_run_id,
              from_step_position: stepSnapshot.position,
            },
          );
          for (const skippedStep of skippedRows) {
            const skippedBlueprintStep = stepsByPosition.get(skippedStep.step_position);
            await emitStepTimelineEvent(internalConfig, {
              orgId: org_id,
              companyId: company_id,
              submissionId: run.submission_id,
              pipelineRunId: pipeline_run_id,
              entityType: entityTypeFromOperationId(operationIdForStep(skippedBlueprintStep)),
              cumulativeContext,
              stepResultId: skippedStep.id,
              stepPosition: skippedStep.step_position,
              operationId: operationIdForStep(skippedBlueprintStep),
              stepStatus: "skipped",
              skipReason: "upstream_step_failed",
              durationMs: skippedStep.duration_ms,
              errorMessage: "Skipped because a prior step failed",
              errorDetails: {
                failed_step_position: stepSnapshot.position,
                failed_operation_id: operationId,
              },
            });
          }
          await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
            pipeline_run_id,
            status: "failed",
            error_message: message,
            error_details: { operation_id: operationId, missing_inputs: result.missing_inputs || [] },
          });
          await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
            submission_id: run.submission_id,
          });
          return { pipeline_run_id, status: "failed", failed_step_position: stepSnapshot.position, error: message };
        }

        const succeededStep = await internalPost<InternalStepResult>(
          internalConfig,
          "/api/internal/step-results/update",
          {
            step_result_id: stepResult.id,
            status: "succeeded",
            output_payload: {
              operation_result: result,
              cumulative_context: cumulativeContext,
            },
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType: stepEntityType,
          cumulativeContext,
          stepResultId: succeededStep.id,
          stepPosition: succeededStep.step_position,
          operationId,
          stepStatus: "succeeded",
          durationMs: succeededStep.duration_ms,
          providerAttempts: Array.isArray(result.provider_attempts) ? result.provider_attempts : [],
          operationResult: result as unknown as Record<string, unknown>,
        });
        lastSuccessfulOperationId = operationId;

        const fanOutEnabled =
          stepSnapshot.fan_out === true ||
          stepSnapshot.step_config?.fan_out === true;
        if (fanOutEnabled) {
          const fanOutEntities = extractFanOutResults(result.output);
          const providerAttempts = Array.isArray(result.provider_attempts)
            ? result.provider_attempts
            : [];
          const fanOutProvider = providerAttempts.find(
            (attempt) => attempt?.status === "found" || attempt?.status === "succeeded",
          )?.provider as string | undefined;

          const fanOutResponse = await internalPost<FanOutChildRunsResponse>(
            internalConfig,
            "/api/internal/pipeline-runs/fan-out",
            {
              parent_pipeline_run_id: pipeline_run_id,
              submission_id: run.submission_id,
              org_id,
              company_id,
              blueprint_snapshot: run.blueprint_snapshot,
              fan_out_entities: fanOutEntities,
              start_from_position: stepSnapshot.position + 1,
              parent_cumulative_context: cumulativeContext,
              fan_out_operation_id: operationId,
              provider: fanOutProvider ?? null,
              provider_attempts: providerAttempts,
            },
          );

          await internalPost(internalConfig, "/api/internal/step-results/update", {
            step_result_id: stepResult.id,
            status: "succeeded",
            output_payload: {
              operation_result: result,
              cumulative_context: cumulativeContext,
              fan_out: {
                child_run_ids: fanOutResponse.child_run_ids,
                child_count: fanOutResponse.child_run_ids.length,
                child_count_created: fanOutResponse.child_run_ids.length,
                child_count_skipped_duplicates: fanOutResponse.skipped_duplicates_count ?? 0,
                skipped_duplicate_identifiers: fanOutResponse.skipped_duplicate_identifiers ?? [],
                start_from_position: stepSnapshot.position + 1,
              },
            },
          });

          await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
            pipeline_run_id,
            status: "succeeded",
            error_message: null,
            error_details: null,
          });
          try {
            await internalPost(internalConfig, "/api/internal/entity-state/upsert", {
              pipeline_run_id,
              entity_type: entityType,
              cumulative_context: cumulativeContext,
              last_operation_id: lastSuccessfulOperationId,
            });
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
              pipeline_run_id,
              status: "failed",
              error_message: "Entity state upsert failed",
              error_details: { error: message },
            });
            await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
              submission_id: run.submission_id,
            });
            return { pipeline_run_id, status: "failed", error: message };
          }
          await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
            submission_id: run.submission_id,
          });
          return {
            pipeline_run_id,
            status: "succeeded",
            fan_out_child_run_ids: fanOutResponse.child_run_ids,
            fan_out_child_count: fanOutResponse.child_run_ids.length,
          };
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const failedStep = await internalPost<InternalStepResult>(
          internalConfig,
          "/api/internal/step-results/update",
          {
            step_result_id: stepResult.id,
            status: "failed",
            error_message: message,
            error_details: { error: message },
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType: entityTypeFromOperationId(operationId),
          cumulativeContext,
          stepResultId: failedStep.id,
          stepPosition: failedStep.step_position,
          operationId,
          stepStatus: "failed",
          durationMs: failedStep.duration_ms,
          errorMessage: message,
          errorDetails: { error: message },
        });
        const skippedRows = await internalPost<Array<InternalStepResult>>(
          internalConfig,
          "/api/internal/step-results/mark-remaining-skipped",
          {
            pipeline_run_id,
            from_step_position: stepSnapshot.position,
          },
        );
        for (const skippedStep of skippedRows) {
          const skippedBlueprintStep = stepsByPosition.get(skippedStep.step_position);
          await emitStepTimelineEvent(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            submissionId: run.submission_id,
            pipelineRunId: pipeline_run_id,
            entityType: entityTypeFromOperationId(operationIdForStep(skippedBlueprintStep)),
            cumulativeContext,
            stepResultId: skippedStep.id,
            stepPosition: skippedStep.step_position,
            operationId: operationIdForStep(skippedBlueprintStep),
            stepStatus: "skipped",
            skipReason: "upstream_step_failed",
            durationMs: skippedStep.duration_ms,
            errorMessage: "Skipped because a prior step failed",
            errorDetails: {
              failed_step_position: stepSnapshot.position,
              failed_operation_id: operationId,
            },
          });
        }
        await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
          pipeline_run_id,
          status: "failed",
          error_message: message,
          error_details: { error: message },
        });
        await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
          submission_id: run.submission_id,
        });
        return { pipeline_run_id, status: "failed", failed_step_position: stepSnapshot.position, error: message };
      }
    }

    await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
      pipeline_run_id,
      status: "succeeded",
      error_message: null,
      error_details: null,
    });
    try {
      await internalPost(internalConfig, "/api/internal/entity-state/upsert", {
        pipeline_run_id,
        entity_type: entityType,
        cumulative_context: cumulativeContext,
        last_operation_id: lastSuccessfulOperationId,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
        pipeline_run_id,
        status: "failed",
        error_message: "Entity state upsert failed",
        error_details: { error: message },
      });
      await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
        submission_id: run.submission_id,
      });
      return { pipeline_run_id, status: "failed", error: message };
    }
    await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
      submission_id: run.submission_id,
    });
    return { pipeline_run_id, status: "succeeded" };
  },
});

export const __testables = {
  extractFreshnessIdentifiers,
  getSkipIfFreshConfig,
  inferFieldsUpdatedFromOperationResult,
  operationIdForStep,
};
