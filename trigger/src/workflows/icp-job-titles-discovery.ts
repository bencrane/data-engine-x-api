import { logger } from "@trigger.dev/sdk/v3";

import { buildCompanySeedContext, mergeStepOutput, WorkflowContext } from "./context.js";
import { createInternalApiClient, InternalApiClient } from "./internal-api.js";
import {
  markPipelineRunFailed,
  markPipelineRunRunning,
  markPipelineRunSucceeded,
  markStepResultFailed,
  markStepResultRunning,
  markStepResultSucceeded,
  WorkflowStepReference,
} from "./lineage.js";
import {
  DEFAULT_PARALLEL_POLLING_SCHEDULE_MS,
  ParallelDeepResearchError,
  SleepFn,
  runParallelDeepResearch,
} from "./parallel-deep-research.js";
import { OperationExecutionResult } from "./operations.js";
import {
  EntityStateUpsertResult,
  upsertEntityStateConfirmed,
  writeDedicatedTableConfirmed,
} from "./persistence.js";
import { renderIcpJobTitlesPrompt } from "./prompts/icp-job-titles.js";

type IcpJobTitlesWorkflowOperationId = "company.derive.icp_job_titles";

const ICP_JOB_TITLES_OPERATION_ID: IcpJobTitlesWorkflowOperationId = "company.derive.icp_job_titles";
const ICP_JOB_TITLES_PROVIDER_ACTION = "deep_research_icp_job_titles";

interface IcpJobTitlesWorkflowDefinitionStep {
  position: number;
  operationId: IcpJobTitlesWorkflowOperationId;
}

interface IcpJobTitlesDedicatedWriteResult {
  id?: string;
  company_domain: string;
  [key: string]: unknown;
}

interface PersistenceOutcome {
  entityStateConfirmed: boolean;
  entityId?: string;
  icpJobTitlesConfirmed: boolean;
  icpJobTitlesId?: string;
  errors: string[];
  errorDetails: Record<string, unknown>;
}

export interface IcpJobTitlesDiscoveryWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  company_domain: string;
  submission_id?: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;
  company_name?: string;
  company_description?: string;
  processor?: string;
  api_url?: string;
  internal_api_key?: string;
}

export interface IcpJobTitlesDiscoveryWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  entity_id?: string;
  icp_job_titles_id?: string;
  last_operation_id?: IcpJobTitlesWorkflowOperationId | null;
  error?: string;
  executed_steps: Array<{
    step_position: number;
    operation_id: IcpJobTitlesWorkflowOperationId;
    status: "succeeded";
    operation_status?: string;
  }>;
  persistence: {
    entity_state_confirmed: boolean;
    icp_job_titles_confirmed: boolean;
  };
}

export interface IcpJobTitlesDiscoveryWorkflowDependencies {
  client?: InternalApiClient;
  parallelFetchImpl?: typeof fetch;
  parallelSleep?: SleepFn;
  parallelApiKey?: string;
}

const ICP_JOB_TITLES_DISCOVERY_STEPS: IcpJobTitlesWorkflowDefinitionStep[] = [
  {
    position: 1,
    operationId: ICP_JOB_TITLES_OPERATION_ID,
  },
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getOptionalString(value: unknown): string | undefined {
  if (typeof value !== "string") {
    return undefined;
  }

  const normalized = value.trim();
  return normalized.length > 0 ? normalized : undefined;
}

function getStepReferenceMap(
  stepResults: WorkflowStepReference[],
): Map<number, WorkflowStepReference> {
  const stepReferenceMap = new Map<number, WorkflowStepReference>();

  for (const stepResult of stepResults) {
    if (stepReferenceMap.has(stepResult.step_position)) {
      throw new Error(`Duplicate step_result mapping for position ${stepResult.step_position}`);
    }
    stepReferenceMap.set(stepResult.step_position, stepResult);
  }

  return stepReferenceMap;
}

function validateWorkflowStepReferences(stepResults: WorkflowStepReference[]): void {
  const expectedPositions = ICP_JOB_TITLES_DISCOVERY_STEPS.map((step) => step.position).sort(
    (a, b) => a - b,
  );
  const actualPositions = stepResults.map((step) => step.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `ICP job titles discovery workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  for (let index = 0; index < expectedPositions.length; index += 1) {
    if (expectedPositions[index] !== actualPositions[index]) {
      throw new Error(
        `ICP job titles discovery workflow step_results must match positions ${expectedPositions.join(", ")}`,
      );
    }
  }
}

function getClient(
  payload: IcpJobTitlesDiscoveryWorkflowPayload,
  dependencies: IcpJobTitlesDiscoveryWorkflowDependencies,
): InternalApiClient {
  return (
    dependencies.client ??
    createInternalApiClient({
      authContext: {
        orgId: payload.org_id,
        companyId: payload.company_id,
      },
      apiUrl: payload.api_url,
      internalApiKey: payload.internal_api_key,
    })
  );
}

function extractStructuredParallelOutput(parallelRawResponse: Record<string, unknown>): Record<string, unknown> {
  const output = parallelRawResponse.output;
  if (!isRecord(output)) {
    throw new Error("Parallel result is missing output");
  }

  const content = output.content;
  if (!isRecord(content) || Object.keys(content).length === 0) {
    throw new Error("Parallel result is missing output.content");
  }

  return content;
}

function buildWorkflowOutput(params: {
  companyDomain: string;
  companyName?: string;
  companyDescription?: string;
  processor: string;
  parallelRunId: string;
  parallelRawResponse: Record<string, unknown>;
  rawParallelOutput: Record<string, unknown>;
}): WorkflowContext {
  const inferredProduct =
    getOptionalString(params.rawParallelOutput.inferredProduct) ??
    getOptionalString(params.rawParallelOutput.inferred_product);
  const buyerPersonaSummary =
    getOptionalString(params.rawParallelOutput.buyerPersonaSummary) ??
    getOptionalString(params.rawParallelOutput.buyer_persona_summary);
  const titles = Array.isArray(params.rawParallelOutput.titles) ? params.rawParallelOutput.titles : undefined;

  return {
    domain: params.companyDomain,
    company_domain: params.companyDomain,
    canonical_domain: params.companyDomain,
    ...(params.companyName ? { company_name: params.companyName } : {}),
    ...(params.companyDescription ? { company_description: params.companyDescription } : {}),
    parallel_run_id: params.parallelRunId,
    processor: params.processor,
    parallel_raw_response: params.parallelRawResponse,
    raw_parallel_output: params.rawParallelOutput,
    ...(inferredProduct ? { inferred_product: inferredProduct } : {}),
    ...(buyerPersonaSummary ? { buyer_persona_summary: buyerPersonaSummary } : {}),
    ...(titles ? { icp_titles: titles } : {}),
  };
}

function buildSuccessfulOperationResult(params: {
  companyDomain: string;
  companyName?: string;
  companyDescription?: string;
  processor: string;
  parallelRunId: string;
  pollCount: number;
  elapsedMs: number;
  parallelRawResponse: Record<string, unknown>;
  rawParallelOutput: Record<string, unknown>;
}): OperationExecutionResult {
  return {
    run_id: params.parallelRunId,
    operation_id: ICP_JOB_TITLES_OPERATION_ID,
    status: "found",
    output: buildWorkflowOutput({
      companyDomain: params.companyDomain,
      companyName: params.companyName,
      companyDescription: params.companyDescription,
      processor: params.processor,
      parallelRunId: params.parallelRunId,
      parallelRawResponse: params.parallelRawResponse,
      rawParallelOutput: params.rawParallelOutput,
    }),
    provider_attempts: [
      {
        provider: "parallel",
        action: ICP_JOB_TITLES_PROVIDER_ACTION,
        status: "found",
        parallel_run_id: params.parallelRunId,
        processor: params.processor,
        poll_count: params.pollCount,
        elapsed_ms: params.elapsedMs,
      },
    ],
  };
}

function buildFailedOperationResult(
  error: unknown,
  context: WorkflowContext,
): OperationExecutionResult {
  if (error instanceof ParallelDeepResearchError) {
    const providerAttempt: Record<string, unknown> = {
      provider: "parallel",
      action: ICP_JOB_TITLES_PROVIDER_ACTION,
      status: error.phase === "config" ? "skipped" : "failed",
      parallel_run_id: error.parallelRunId ?? undefined,
      poll_count: error.pollCount,
      elapsed_ms: error.elapsedMs,
      terminal_status: error.terminalStatus ?? undefined,
      error_phase: error.phase,
      error: error.message,
    };
    if (error.statusCode !== null) {
      providerAttempt.status_code = error.statusCode;
    }
    if (error.responseBody !== undefined) {
      providerAttempt.raw_response = error.responseBody;
    }

    return {
      run_id: error.parallelRunId ?? `${ICP_JOB_TITLES_OPERATION_ID}:failed`,
      operation_id: ICP_JOB_TITLES_OPERATION_ID,
      status: "failed",
      output: {
        company_domain: context.company_domain,
        parallel_run_id: error.parallelRunId ?? undefined,
      },
      provider_attempts: [providerAttempt],
    };
  }

  return {
    run_id: `${ICP_JOB_TITLES_OPERATION_ID}:failed`,
    operation_id: ICP_JOB_TITLES_OPERATION_ID,
    status: "failed",
    output: {
      company_domain: context.company_domain,
    },
    provider_attempts: [
      {
        provider: "parallel",
        action: ICP_JOB_TITLES_PROVIDER_ACTION,
        status: "failed",
        error: error instanceof Error ? error.message : String(error),
      },
    ],
  };
}

async function writeIcpJobTitlesConfirmed(
  client: InternalApiClient,
  params: {
    companyDomain: string;
    companyName?: string;
    companyDescription?: string;
    rawParallelOutput: Record<string, unknown>;
    parallelRunId: string;
    processor: string;
    submissionId?: string;
    pipelineRunId: string;
  },
): Promise<IcpJobTitlesDedicatedWriteResult> {
  return writeDedicatedTableConfirmed<IcpJobTitlesDedicatedWriteResult>(client, {
    path: "/api/internal/icp-job-titles/upsert",
    payload: {
      company_domain: params.companyDomain,
      company_name: params.companyName,
      company_description: params.companyDescription,
      raw_parallel_output: params.rawParallelOutput,
      parallel_run_id: params.parallelRunId,
      processor: params.processor,
      source_submission_id: params.submissionId,
      source_pipeline_run_id: params.pipelineRunId,
    },
    validate: (response) =>
      isRecord(response) &&
      typeof response.company_domain === "string" &&
      response.company_domain.toLowerCase() === params.companyDomain.toLowerCase(),
    confirmationErrorMessage: "ICP job titles dedicated-table write could not be confirmed",
  });
}

async function failWorkflow(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  stepReference?: WorkflowStepReference;
  cumulativeContext: WorkflowContext;
  executedSteps: IcpJobTitlesDiscoveryWorkflowResult["executed_steps"];
  message: string;
  failedOperationResult?: OperationExecutionResult;
  errorDetails?: Record<string, unknown>;
  persistence?: IcpJobTitlesDiscoveryWorkflowResult["persistence"];
}): Promise<IcpJobTitlesDiscoveryWorkflowResult> {
  if (params.stepReference) {
    await markStepResultFailed(params.client, {
      stepResultId: params.stepReference.step_result_id,
      inputPayload: params.cumulativeContext,
      operationResult: params.failedOperationResult,
      cumulativeContext: params.cumulativeContext,
      errorMessage: params.message,
      errorDetails: params.errorDetails ?? null,
    });
  }

  await markPipelineRunFailed(params.client, {
    pipelineRunId: params.pipelineRunId,
    errorMessage: params.message,
    errorDetails: params.errorDetails ?? null,
  });

  return {
    pipeline_run_id: params.pipelineRunId,
    status: "failed",
    cumulative_context: params.cumulativeContext,
    last_operation_id:
      params.executedSteps.length > 0 ? params.executedSteps[params.executedSteps.length - 1]?.operation_id : null,
    error: params.message,
    executed_steps: params.executedSteps,
    persistence:
      params.persistence ?? {
        entity_state_confirmed: false,
        icp_job_titles_confirmed: false,
      },
  };
}

async function persistIcpJobTitlesResults(params: {
  client: InternalApiClient;
  payload: IcpJobTitlesDiscoveryWorkflowPayload;
  cumulativeContext: WorkflowContext;
  processor: string;
  parallelRunId: string;
  rawParallelOutput: Record<string, unknown>;
}): Promise<PersistenceOutcome> {
  const outcome: PersistenceOutcome = {
    entityStateConfirmed: false,
    icpJobTitlesConfirmed: false,
    errors: [],
    errorDetails: {},
  };

  try {
    const entityState = await upsertEntityStateConfirmed(params.client, {
      pipelineRunId: params.payload.pipeline_run_id,
      entityType: "company",
      cumulativeContext: params.cumulativeContext,
      lastOperationId: ICP_JOB_TITLES_OPERATION_ID,
    });
    outcome.entityStateConfirmed = true;
    outcome.entityId = entityState.entity_id;
  } catch (error) {
    outcome.errors.push(
      error instanceof Error ? `Entity state upsert failed: ${error.message}` : `Entity state upsert failed: ${String(error)}`,
    );
    outcome.errorDetails.entity_state = {
      confirmed: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }

  try {
    const icpJobTitlesRow = await writeIcpJobTitlesConfirmed(params.client, {
      companyDomain: String(params.cumulativeContext.company_domain ?? params.payload.company_domain),
      companyName: getOptionalString(params.cumulativeContext.company_name),
      companyDescription: getOptionalString(params.cumulativeContext.company_description),
      rawParallelOutput: params.rawParallelOutput,
      parallelRunId: params.parallelRunId,
      processor: params.processor,
      submissionId: params.payload.submission_id,
      pipelineRunId: params.payload.pipeline_run_id,
    });
    outcome.icpJobTitlesConfirmed = true;
    outcome.icpJobTitlesId = getOptionalString(icpJobTitlesRow.id);
  } catch (error) {
    outcome.errors.push(
      error instanceof Error
        ? `ICP job titles upsert failed: ${error.message}`
        : `ICP job titles upsert failed: ${String(error)}`,
    );
    outcome.errorDetails.icp_job_titles = {
      confirmed: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }

  if (outcome.entityStateConfirmed) {
    outcome.errorDetails.entity_state = {
      confirmed: true,
      entity_id: outcome.entityId,
    };
  }
  if (outcome.icpJobTitlesConfirmed) {
    outcome.errorDetails.icp_job_titles = {
      confirmed: true,
      id: outcome.icpJobTitlesId,
    };
  }

  return outcome;
}

export async function runIcpJobTitlesDiscoveryWorkflow(
  payload: IcpJobTitlesDiscoveryWorkflowPayload,
  dependencies: IcpJobTitlesDiscoveryWorkflowDependencies = {},
): Promise<IcpJobTitlesDiscoveryWorkflowResult> {
  const client = getClient(payload, dependencies);
  const executedSteps: IcpJobTitlesDiscoveryWorkflowResult["executed_steps"] = [];
  let cumulativeContext: WorkflowContext;

  try {
    cumulativeContext = buildCompanySeedContext(payload.company_domain, payload.initial_context ?? {});
    cumulativeContext = mergeStepOutput(cumulativeContext, {
      ...(getOptionalString(payload.company_name) ? { company_name: getOptionalString(payload.company_name) } : {}),
      ...(getOptionalString(payload.company_description)
        ? { company_description: getOptionalString(payload.company_description) }
        : {}),
    });
  } catch (error) {
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage:
        error instanceof Error
          ? `Invalid ICP job titles workflow input: ${error.message}`
          : `Invalid ICP job titles workflow input: ${String(error)}`,
      errorDetails: {
        operation_id: ICP_JOB_TITLES_OPERATION_ID,
      },
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: {},
      error:
        error instanceof Error
          ? `Invalid ICP job titles workflow input: ${error.message}`
          : `Invalid ICP job titles workflow input: ${String(error)}`,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: false,
        icp_job_titles_confirmed: false,
      },
    };
  }

  await markPipelineRunRunning(client, payload.pipeline_run_id);
  try {
    validateWorkflowStepReferences(payload.step_results);
  } catch (error) {
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage:
        error instanceof Error
          ? error.message
          : `ICP job titles workflow validation failed: ${String(error)}`,
      errorDetails: {
        operation_id: ICP_JOB_TITLES_OPERATION_ID,
      },
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      error:
        error instanceof Error
          ? error.message
          : `ICP job titles workflow validation failed: ${String(error)}`,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: false,
        icp_job_titles_confirmed: false,
      },
    };
  }

  const stepReferenceMap = getStepReferenceMap(payload.step_results);
  const step = ICP_JOB_TITLES_DISCOVERY_STEPS[0];
  const stepReference = stepReferenceMap.get(step.position);
  if (!stepReference) {
    return failWorkflow({
      client,
      pipelineRunId: payload.pipeline_run_id,
      cumulativeContext,
      executedSteps,
      message: `Missing step_result mapping for position ${step.position}`,
      errorDetails: { step_position: step.position, operation_id: step.operationId },
    });
  }

  logger.info("icp-job-titles discovery workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    company_domain: cumulativeContext.company_domain,
    processor: payload.processor ?? "pro",
    polling_schedule_ms: DEFAULT_PARALLEL_POLLING_SCHEDULE_MS,
  });

  await markStepResultRunning(client, {
    stepResultId: stepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  let operationResult: OperationExecutionResult;
  let rawParallelOutput: Record<string, unknown>;

  try {
    const prompt = renderIcpJobTitlesPrompt({
      companyDomain: String(cumulativeContext.company_domain ?? payload.company_domain),
      companyName: getOptionalString(cumulativeContext.company_name),
      companyDescription: getOptionalString(cumulativeContext.company_description),
    });

    const parallelResult = await runParallelDeepResearch<Record<string, unknown>>({
      prompt,
      processor: payload.processor,
      operationId: ICP_JOB_TITLES_OPERATION_ID,
      providerAction: ICP_JOB_TITLES_PROVIDER_ACTION,
      apiKey: dependencies.parallelApiKey,
      fetchImpl: dependencies.parallelFetchImpl,
      sleep: dependencies.parallelSleep,
      extractOutput: (result) => extractStructuredParallelOutput(result),
    });

    rawParallelOutput = parallelResult.extractedOutput;
    operationResult = buildSuccessfulOperationResult({
      companyDomain: String(cumulativeContext.company_domain ?? payload.company_domain),
      companyName: getOptionalString(cumulativeContext.company_name),
      companyDescription: getOptionalString(cumulativeContext.company_description),
      processor: parallelResult.processor,
      parallelRunId: parallelResult.parallelRunId,
      pollCount: parallelResult.pollCount,
      elapsedMs: parallelResult.elapsedMs,
      parallelRawResponse: parallelResult.rawResult,
      rawParallelOutput,
    });
  } catch (error) {
    const failedOperationResult = buildFailedOperationResult(error, cumulativeContext);
    return failWorkflow({
      client,
      pipelineRunId: payload.pipeline_run_id,
      stepReference,
      cumulativeContext,
      executedSteps,
      message:
        error instanceof Error
          ? `ICP job titles discovery failed: ${error.message}`
          : `ICP job titles discovery failed: ${String(error)}`,
      failedOperationResult,
      errorDetails: {
        operation_id: ICP_JOB_TITLES_OPERATION_ID,
        error_phase: error instanceof ParallelDeepResearchError ? error.phase : undefined,
        parallel_run_id: error instanceof ParallelDeepResearchError ? error.parallelRunId : undefined,
      },
    });
  }

  cumulativeContext = mergeStepOutput(cumulativeContext, operationResult.output);

  await markStepResultSucceeded(client, {
    stepResultId: stepReference.step_result_id,
    operationResult,
    cumulativeContext,
  });

  executedSteps.push({
    step_position: step.position,
    operation_id: step.operationId,
    status: "succeeded",
    operation_status: operationResult.status,
  });

  await markPipelineRunSucceeded(client, payload.pipeline_run_id);

  const persistenceOutcome = await persistIcpJobTitlesResults({
    client,
    payload,
    cumulativeContext,
    processor: String(operationResult.output?.processor ?? payload.processor ?? "pro"),
    parallelRunId: String(operationResult.output?.parallel_run_id),
    rawParallelOutput,
  });

  if (!persistenceOutcome.entityStateConfirmed || !persistenceOutcome.icpJobTitlesConfirmed) {
    const message = persistenceOutcome.errors.join("; ");
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: persistenceOutcome.errorDetails,
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      entity_id: persistenceOutcome.entityId,
      icp_job_titles_id: persistenceOutcome.icpJobTitlesId,
      last_operation_id: ICP_JOB_TITLES_OPERATION_ID,
      error: message,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: persistenceOutcome.entityStateConfirmed,
        icp_job_titles_confirmed: persistenceOutcome.icpJobTitlesConfirmed,
      },
    };
  }

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    entity_id: persistenceOutcome.entityId,
    icp_job_titles_id: persistenceOutcome.icpJobTitlesId,
    last_operation_id: ICP_JOB_TITLES_OPERATION_ID,
    executed_steps: executedSteps,
    persistence: {
      entity_state_confirmed: true,
      icp_job_titles_confirmed: true,
    },
  };
}

export const __testables = {
  ICP_JOB_TITLES_DISCOVERY_STEPS,
  validateWorkflowStepReferences,
  extractStructuredParallelOutput,
};
