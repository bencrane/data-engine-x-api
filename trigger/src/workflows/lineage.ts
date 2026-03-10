import { WorkflowContext } from "./context.js";
import { InternalApiClient } from "./internal-api.js";
import { OperationExecutionResult } from "./operations.js";
import { confirmedInternalWrite } from "./persistence.js";

export type PipelineRunStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";
export type StepResultStatus = "queued" | "running" | "succeeded" | "failed" | "skipped" | "retrying";

export interface PipelineRunRecord {
  id: string;
  status: PipelineRunStatus;
  [key: string]: unknown;
}

export interface StepResultRecord {
  id: string;
  step_position: number;
  status?: string;
  duration_ms?: number | null;
  [key: string]: unknown;
}

export interface WorkflowStepReference {
  step_result_id: string;
  step_position: number;
}

interface UpdatePipelineRunStatusParams {
  pipelineRunId: string;
  status: PipelineRunStatus;
  errorMessage?: string | null;
  errorDetails?: Record<string, unknown> | null;
}

interface UpdateStepResultParams {
  stepResultId: string;
  status: StepResultStatus;
  inputPayload?: Record<string, unknown> | null;
  outputPayload?: Record<string, unknown> | null;
  errorMessage?: string | null;
  errorDetails?: Record<string, unknown> | null;
}

function isPipelineRunRecord(value: unknown, pipelineRunId: string): value is PipelineRunRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>).id === pipelineRunId
  );
}

function isStepResultRecord(value: unknown, stepResultId: string): value is StepResultRecord {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value) &&
    (value as Record<string, unknown>).id === stepResultId
  );
}

function buildOperationOutputPayload(
  operationResult: OperationExecutionResult,
  cumulativeContext: WorkflowContext,
): Record<string, unknown> {
  return {
    operation_result: operationResult,
    cumulative_context: cumulativeContext,
  };
}

async function updatePipelineRunStatus(
  client: InternalApiClient,
  params: UpdatePipelineRunStatusParams,
): Promise<PipelineRunRecord> {
  return confirmedInternalWrite<PipelineRunRecord>(client, {
    path: "/api/internal/pipeline-runs/update-status",
    payload: {
      pipeline_run_id: params.pipelineRunId,
      status: params.status,
      error_message: params.errorMessage ?? undefined,
      error_details: params.errorDetails ?? undefined,
    },
    validate: (response) => isPipelineRunRecord(response, params.pipelineRunId),
    confirmationErrorMessage: `Pipeline run status write could not be confirmed: ${params.pipelineRunId}`,
  });
}

async function updateStepResult(
  client: InternalApiClient,
  params: UpdateStepResultParams,
): Promise<StepResultRecord> {
  return confirmedInternalWrite<StepResultRecord>(client, {
    path: "/api/internal/step-results/update",
    payload: {
      step_result_id: params.stepResultId,
      status: params.status,
      input_payload: params.inputPayload ?? undefined,
      output_payload: params.outputPayload ?? undefined,
      error_message: params.errorMessage ?? undefined,
      error_details: params.errorDetails ?? undefined,
    },
    validate: (response) => isStepResultRecord(response, params.stepResultId),
    confirmationErrorMessage: `Step result write could not be confirmed: ${params.stepResultId}`,
  });
}

export async function markPipelineRunRunning(
  client: InternalApiClient,
  pipelineRunId: string,
): Promise<PipelineRunRecord> {
  return updatePipelineRunStatus(client, {
    pipelineRunId,
    status: "running",
  });
}

export async function markPipelineRunSucceeded(
  client: InternalApiClient,
  pipelineRunId: string,
): Promise<PipelineRunRecord> {
  return updatePipelineRunStatus(client, {
    pipelineRunId,
    status: "succeeded",
    errorMessage: null,
    errorDetails: null,
  });
}

export async function markPipelineRunFailed(
  client: InternalApiClient,
  params: {
    pipelineRunId: string;
    errorMessage: string;
    errorDetails?: Record<string, unknown> | null;
  },
): Promise<PipelineRunRecord> {
  return updatePipelineRunStatus(client, {
    pipelineRunId: params.pipelineRunId,
    status: "failed",
    errorMessage: params.errorMessage,
    errorDetails: params.errorDetails ?? null,
  });
}

export async function markStepResultRunning(
  client: InternalApiClient,
  params: {
    stepResultId: string;
    inputPayload: WorkflowContext;
  },
): Promise<StepResultRecord> {
  return updateStepResult(client, {
    stepResultId: params.stepResultId,
    status: "running",
    inputPayload: params.inputPayload,
  });
}

export async function markStepResultSucceeded(
  client: InternalApiClient,
  params: {
    stepResultId: string;
    operationResult: OperationExecutionResult;
    cumulativeContext: WorkflowContext;
  },
): Promise<StepResultRecord> {
  return updateStepResult(client, {
    stepResultId: params.stepResultId,
    status: "succeeded",
    outputPayload: buildOperationOutputPayload(params.operationResult, params.cumulativeContext),
  });
}

export async function markStepResultFailed(
  client: InternalApiClient,
  params: {
    stepResultId: string;
    inputPayload?: WorkflowContext;
    operationResult?: OperationExecutionResult;
    cumulativeContext?: WorkflowContext;
    errorMessage: string;
    errorDetails?: Record<string, unknown> | null;
  },
): Promise<StepResultRecord> {
  const outputPayload =
    params.operationResult && params.cumulativeContext
      ? buildOperationOutputPayload(params.operationResult, params.cumulativeContext)
      : undefined;

  return updateStepResult(client, {
    stepResultId: params.stepResultId,
    status: "failed",
    inputPayload: params.inputPayload ?? null,
    outputPayload,
    errorMessage: params.errorMessage,
    errorDetails: params.errorDetails ?? null,
  });
}

export async function markStepResultSkipped(
  client: InternalApiClient,
  params: {
    stepResultId: string;
    inputPayload: WorkflowContext;
    skipReason: string;
    metadata?: Record<string, unknown> | null;
  },
): Promise<StepResultRecord> {
  return updateStepResult(client, {
    stepResultId: params.stepResultId,
    status: "skipped",
    inputPayload: params.inputPayload,
    outputPayload: {
      skip_reason: params.skipReason,
      metadata: params.metadata ?? {},
    },
  });
}

export async function skipRemainingWorkflowSteps(
  client: InternalApiClient,
  params: {
    remainingSteps: WorkflowStepReference[];
    cumulativeContext: WorkflowContext;
    failedStepPosition: number;
    failedOperationId: string;
  },
): Promise<StepResultRecord[]> {
  const skippedResults: StepResultRecord[] = [];

  for (const step of params.remainingSteps) {
    const skipped = await markStepResultSkipped(client, {
      stepResultId: step.step_result_id,
      inputPayload: params.cumulativeContext,
      skipReason: "upstream_step_failed",
      metadata: {
        failed_step_position: params.failedStepPosition,
        failed_operation_id: params.failedOperationId,
      },
    });
    skippedResults.push(skipped);
  }

  return skippedResults;
}
