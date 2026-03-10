import { logger } from "@trigger.dev/sdk/v3";

import { buildCompanySeedContext, mergeStepOutput, normalizeCompanyDomain, WorkflowContext } from "./context.js";
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
  ParallelDeepResearchParams,
  ParallelDeepResearchSuccess,
  runParallelDeepResearch,
  SleepFn,
} from "./parallel-deep-research.js";
import { OperationExecutionResult } from "./operations.js";
import {
  EntityStateUpsertResult,
  upsertEntityStateConfirmed,
  writeDedicatedTableConfirmed,
} from "./persistence.js";
import { renderCompanyIntelBriefingPrompt } from "./prompts/company-intel-briefing.js";

type CompanyIntelBriefingWorkflowOperationId = "company.derive.intel_briefing";
type CompanyCompetitors = string | string[] | undefined;

const COMPANY_INTEL_BRIEFING_OPERATION_ID: CompanyIntelBriefingWorkflowOperationId =
  "company.derive.intel_briefing";
const COMPANY_INTEL_BRIEFING_PROVIDER_ACTION = "deep_research_company_intel_briefing";
const DEFAULT_COMPANY_INTEL_BRIEFING_PROCESSOR = "ultra";

interface CompanyIntelBriefingWorkflowDefinitionStep {
  position: number;
  operationId: CompanyIntelBriefingWorkflowOperationId;
}

interface CompanyIntelBriefingDedicatedWriteResult {
  id?: string;
  company_domain: string;
  client_company_name?: string | null;
  [key: string]: unknown;
}

interface PersistenceOutcome {
  entityStateConfirmed: boolean;
  entityId?: string;
  companyIntelBriefingConfirmed: boolean;
  companyIntelBriefingId?: string;
  errors: string[];
  errorDetails: Record<string, unknown>;
}

export interface CompanyIntelBriefingWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  company_domain: string;
  client_company_name: string;
  client_company_domain: string;
  client_company_description: string;
  step_results: WorkflowStepReference[];
  submission_id?: string;
  initial_context?: WorkflowContext;
  company_name?: string;
  company_description?: string;
  company_industry?: string;
  company_size?: string;
  company_funding?: string;
  company_competitors?: CompanyCompetitors;
  processor?: string;
  api_url?: string;
  internal_api_key?: string;
}

export interface CompanyIntelBriefingWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  entity_id?: string;
  company_intel_briefing_id?: string;
  last_operation_id?: CompanyIntelBriefingWorkflowOperationId | null;
  error?: string;
  executed_steps: Array<{
    step_position: number;
    operation_id: CompanyIntelBriefingWorkflowOperationId;
    status: "succeeded";
    operation_status?: string;
  }>;
  persistence: {
    entity_state_confirmed: boolean;
    company_intel_briefing_confirmed: boolean;
  };
}

export type ParallelDeepResearchRunner = <TExtracted>(
  params: ParallelDeepResearchParams<TExtracted>,
) => Promise<ParallelDeepResearchSuccess<TExtracted>>;

export interface CompanyIntelBriefingWorkflowDependencies {
  client?: InternalApiClient;
  parallelFetchImpl?: typeof fetch;
  parallelSleep?: SleepFn;
  parallelApiKey?: string;
  parallelRunner?: ParallelDeepResearchRunner;
}

const COMPANY_INTEL_BRIEFING_STEPS: CompanyIntelBriefingWorkflowDefinitionStep[] = [
  {
    position: 1,
    operationId: COMPANY_INTEL_BRIEFING_OPERATION_ID,
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

function getOptionalCompetitors(value: unknown): CompanyCompetitors {
  if (Array.isArray(value)) {
    const normalized = value
      .map((item) => getOptionalString(item))
      .filter((item): item is string => item !== undefined);
    return normalized.length > 0 ? normalized : undefined;
  }

  return getOptionalString(value);
}

function requireContextString(value: unknown, fieldName: string): string {
  const normalized = getOptionalString(value);
  if (!normalized) {
    throw new Error(`${fieldName} is required`);
  }
  return normalized;
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
  const expectedPositions = COMPANY_INTEL_BRIEFING_STEPS.map((step) => step.position).sort(
    (a, b) => a - b,
  );
  const actualPositions = stepResults.map((step) => step.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `Company intel briefing workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  for (let index = 0; index < expectedPositions.length; index += 1) {
    if (expectedPositions[index] !== actualPositions[index]) {
      throw new Error(
        `Company intel briefing workflow step_results must match positions ${expectedPositions.join(", ")}`,
      );
    }
  }
}

function getClient(
  payload: CompanyIntelBriefingWorkflowPayload,
  dependencies: CompanyIntelBriefingWorkflowDependencies,
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

function getParallelRunner(
  dependencies: CompanyIntelBriefingWorkflowDependencies,
): ParallelDeepResearchRunner {
  return dependencies.parallelRunner ?? runParallelDeepResearch;
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
  companyIndustry?: string;
  companySize?: string;
  companyFunding?: string;
  companyCompetitors?: CompanyCompetitors;
  clientCompanyName: string;
  clientCompanyDomain: string;
  clientCompanyDescription: string;
  processor: string;
  parallelRunId: string;
  parallelRawResponse: Record<string, unknown>;
  rawParallelOutput: Record<string, unknown>;
}): WorkflowContext {
  const normalizedCompetitors =
    Array.isArray(params.companyCompetitors) && params.companyCompetitors.length > 0
      ? params.companyCompetitors
      : typeof params.companyCompetitors === "string"
        ? params.companyCompetitors
        : undefined;

  return {
    domain: params.companyDomain,
    company_domain: params.companyDomain,
    canonical_domain: params.companyDomain,
    ...(params.companyName ? { company_name: params.companyName } : {}),
    ...(params.companyDescription ? { company_description: params.companyDescription } : {}),
    ...(params.companyIndustry ? { company_industry: params.companyIndustry } : {}),
    ...(params.companySize ? { company_size: params.companySize } : {}),
    ...(params.companyFunding ? { company_funding: params.companyFunding } : {}),
    ...(normalizedCompetitors ? { company_competitors: normalizedCompetitors } : {}),
    client_company_name: params.clientCompanyName,
    client_company_domain: params.clientCompanyDomain,
    client_company_description: params.clientCompanyDescription,
    target_company_domain: params.companyDomain,
    ...(params.companyName ? { target_company_name: params.companyName } : {}),
    ...(params.companyDescription ? { target_company_description: params.companyDescription } : {}),
    ...(params.companyIndustry ? { target_company_industry: params.companyIndustry } : {}),
    ...(params.companySize ? { target_company_size: params.companySize } : {}),
    ...(params.companyFunding ? { target_company_funding: params.companyFunding } : {}),
    ...(normalizedCompetitors ? { target_company_competitors: normalizedCompetitors } : {}),
    parallel_run_id: params.parallelRunId,
    processor: params.processor,
    parallel_raw_response: params.parallelRawResponse,
    raw_parallel_output: params.rawParallelOutput,
  };
}

function buildSuccessfulOperationResult(params: {
  companyDomain: string;
  companyName?: string;
  companyDescription?: string;
  companyIndustry?: string;
  companySize?: string;
  companyFunding?: string;
  companyCompetitors?: CompanyCompetitors;
  clientCompanyName: string;
  clientCompanyDomain: string;
  clientCompanyDescription: string;
  processor: string;
  parallelRunId: string;
  pollCount: number;
  elapsedMs: number;
  parallelRawResponse: Record<string, unknown>;
  rawParallelOutput: Record<string, unknown>;
}): OperationExecutionResult {
  return {
    run_id: params.parallelRunId,
    operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
    status: "found",
    output: buildWorkflowOutput({
      companyDomain: params.companyDomain,
      companyName: params.companyName,
      companyDescription: params.companyDescription,
      companyIndustry: params.companyIndustry,
      companySize: params.companySize,
      companyFunding: params.companyFunding,
      companyCompetitors: params.companyCompetitors,
      clientCompanyName: params.clientCompanyName,
      clientCompanyDomain: params.clientCompanyDomain,
      clientCompanyDescription: params.clientCompanyDescription,
      processor: params.processor,
      parallelRunId: params.parallelRunId,
      parallelRawResponse: params.parallelRawResponse,
      rawParallelOutput: params.rawParallelOutput,
    }),
    provider_attempts: [
      {
        provider: "parallel",
        action: COMPANY_INTEL_BRIEFING_PROVIDER_ACTION,
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
      action: COMPANY_INTEL_BRIEFING_PROVIDER_ACTION,
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
      run_id: error.parallelRunId ?? `${COMPANY_INTEL_BRIEFING_OPERATION_ID}:failed`,
      operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
      status: "failed",
      output: {
        company_domain: context.company_domain,
        parallel_run_id: error.parallelRunId ?? undefined,
        client_company_name: context.client_company_name,
      },
      provider_attempts: [providerAttempt],
    };
  }

  return {
    run_id: `${COMPANY_INTEL_BRIEFING_OPERATION_ID}:failed`,
    operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
    status: "failed",
    output: {
      company_domain: context.company_domain,
      client_company_name: context.client_company_name,
    },
    provider_attempts: [
      {
        provider: "parallel",
        action: COMPANY_INTEL_BRIEFING_PROVIDER_ACTION,
        status: "failed",
        error: error instanceof Error ? error.message : String(error),
      },
    ],
  };
}

async function writeCompanyIntelBriefingConfirmed(
  client: InternalApiClient,
  params: {
    companyDomain: string;
    companyName?: string;
    clientCompanyName: string;
    clientCompanyDomain: string;
    clientCompanyDescription: string;
    rawParallelOutput: Record<string, unknown>;
    parallelRunId: string;
    processor: string;
    submissionId?: string;
    pipelineRunId: string;
  },
): Promise<CompanyIntelBriefingDedicatedWriteResult> {
  return writeDedicatedTableConfirmed<CompanyIntelBriefingDedicatedWriteResult>(client, {
    path: "/api/internal/company-intel-briefings/upsert",
    payload: {
      company_domain: params.companyDomain,
      company_name: params.companyName,
      client_company_name: params.clientCompanyName,
      client_company_domain: params.clientCompanyDomain,
      client_company_description: params.clientCompanyDescription,
      raw_parallel_output: params.rawParallelOutput,
      parallel_run_id: params.parallelRunId,
      processor: params.processor,
      source_submission_id: params.submissionId,
      source_pipeline_run_id: params.pipelineRunId,
    },
    validate: (response) =>
      isRecord(response) &&
      typeof response.company_domain === "string" &&
      response.company_domain.toLowerCase() === params.companyDomain.toLowerCase() &&
      (response.client_company_name == null || response.client_company_name === params.clientCompanyName),
    confirmationErrorMessage: "Company intel briefing dedicated-table write could not be confirmed",
  });
}

async function failWorkflow(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  stepReference?: WorkflowStepReference;
  cumulativeContext: WorkflowContext;
  executedSteps: CompanyIntelBriefingWorkflowResult["executed_steps"];
  message: string;
  failedOperationResult?: OperationExecutionResult;
  errorDetails?: Record<string, unknown>;
  persistence?: CompanyIntelBriefingWorkflowResult["persistence"];
}): Promise<CompanyIntelBriefingWorkflowResult> {
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
        company_intel_briefing_confirmed: false,
      },
  };
}

async function persistCompanyIntelBriefingResults(params: {
  client: InternalApiClient;
  payload: CompanyIntelBriefingWorkflowPayload;
  cumulativeContext: WorkflowContext;
  processor: string;
  parallelRunId: string;
  rawParallelOutput: Record<string, unknown>;
}): Promise<PersistenceOutcome> {
  const outcome: PersistenceOutcome = {
    entityStateConfirmed: false,
    companyIntelBriefingConfirmed: false,
    errors: [],
    errorDetails: {},
  };

  try {
    const entityState: EntityStateUpsertResult = await upsertEntityStateConfirmed(params.client, {
      pipelineRunId: params.payload.pipeline_run_id,
      entityType: "company",
      cumulativeContext: params.cumulativeContext,
      lastOperationId: COMPANY_INTEL_BRIEFING_OPERATION_ID,
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
    const companyIntelBriefingRow = await writeCompanyIntelBriefingConfirmed(params.client, {
      companyDomain: String(params.cumulativeContext.company_domain ?? params.payload.company_domain),
      companyName: getOptionalString(params.cumulativeContext.company_name),
      clientCompanyName: requireContextString(
        params.cumulativeContext.client_company_name,
        "client_company_name",
      ),
      clientCompanyDomain: normalizeCompanyDomain(
        requireContextString(params.cumulativeContext.client_company_domain, "client_company_domain"),
      ),
      clientCompanyDescription: requireContextString(
        params.cumulativeContext.client_company_description,
        "client_company_description",
      ),
      rawParallelOutput: params.rawParallelOutput,
      parallelRunId: params.parallelRunId,
      processor: params.processor,
      submissionId: params.payload.submission_id,
      pipelineRunId: params.payload.pipeline_run_id,
    });
    outcome.companyIntelBriefingConfirmed = true;
    outcome.companyIntelBriefingId = getOptionalString(companyIntelBriefingRow.id);
  } catch (error) {
    outcome.errors.push(
      error instanceof Error
        ? `Company intel briefing upsert failed: ${error.message}`
        : `Company intel briefing upsert failed: ${String(error)}`,
    );
    outcome.errorDetails.company_intel_briefing = {
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
  if (outcome.companyIntelBriefingConfirmed) {
    outcome.errorDetails.company_intel_briefing = {
      confirmed: true,
      id: outcome.companyIntelBriefingId,
    };
  }

  return outcome;
}

export async function runCompanyIntelBriefingWorkflow(
  payload: CompanyIntelBriefingWorkflowPayload,
  dependencies: CompanyIntelBriefingWorkflowDependencies = {},
): Promise<CompanyIntelBriefingWorkflowResult> {
  const client = getClient(payload, dependencies);
  const parallelRunner = getParallelRunner(dependencies);
  const executedSteps: CompanyIntelBriefingWorkflowResult["executed_steps"] = [];
  let cumulativeContext: WorkflowContext;

  try {
    cumulativeContext = buildCompanySeedContext(payload.company_domain, payload.initial_context ?? {});
    cumulativeContext = mergeStepOutput(cumulativeContext, {
      ...(getOptionalString(payload.company_name) ? { company_name: getOptionalString(payload.company_name) } : {}),
      ...(getOptionalString(payload.company_description)
        ? { company_description: getOptionalString(payload.company_description) }
        : {}),
      ...(getOptionalString(payload.company_industry)
        ? { company_industry: getOptionalString(payload.company_industry) }
        : {}),
      ...(getOptionalString(payload.company_size) ? { company_size: getOptionalString(payload.company_size) } : {}),
      ...(getOptionalString(payload.company_funding)
        ? { company_funding: getOptionalString(payload.company_funding) }
        : {}),
      ...(getOptionalCompetitors(payload.company_competitors)
        ? { company_competitors: getOptionalCompetitors(payload.company_competitors) }
        : {}),
      client_company_name: requireContextString(payload.client_company_name, "client_company_name"),
      client_company_domain: normalizeCompanyDomain(
        requireContextString(payload.client_company_domain, "client_company_domain"),
      ),
      client_company_description: requireContextString(
        payload.client_company_description,
        "client_company_description",
      ),
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? `Invalid company intel briefing workflow input: ${error.message}`
        : `Invalid company intel briefing workflow input: ${String(error)}`;

    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
      },
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: {},
      error: message,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: false,
        company_intel_briefing_confirmed: false,
      },
    };
  }

  await markPipelineRunRunning(client, payload.pipeline_run_id);
  try {
    validateWorkflowStepReferences(payload.step_results);
  } catch (error) {
    const message =
      error instanceof Error
        ? error.message
        : `Company intel briefing workflow validation failed: ${String(error)}`;

    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
      },
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      error: message,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: false,
        company_intel_briefing_confirmed: false,
      },
    };
  }

  const stepReferenceMap = getStepReferenceMap(payload.step_results);
  const step = COMPANY_INTEL_BRIEFING_STEPS[0];
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

  logger.info("company-intel-briefing workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    company_domain: cumulativeContext.company_domain,
    client_company_name: cumulativeContext.client_company_name,
    processor: payload.processor ?? DEFAULT_COMPANY_INTEL_BRIEFING_PROCESSOR,
    polling_schedule_ms: DEFAULT_PARALLEL_POLLING_SCHEDULE_MS,
  });

  await markStepResultRunning(client, {
    stepResultId: stepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  let operationResult: OperationExecutionResult;
  let rawParallelOutput: Record<string, unknown>;

  try {
    const prompt = renderCompanyIntelBriefingPrompt({
      companyDomain: String(cumulativeContext.company_domain ?? payload.company_domain),
      companyName: getOptionalString(cumulativeContext.company_name),
      companyDescription: getOptionalString(cumulativeContext.company_description),
      companyIndustry: getOptionalString(cumulativeContext.company_industry),
      companySize: getOptionalString(cumulativeContext.company_size),
      companyFunding: getOptionalString(cumulativeContext.company_funding),
      companyCompetitors: getOptionalCompetitors(cumulativeContext.company_competitors),
      clientCompanyName: requireContextString(
        cumulativeContext.client_company_name,
        "client_company_name",
      ),
      clientCompanyDomain: requireContextString(
        cumulativeContext.client_company_domain,
        "client_company_domain",
      ),
      clientCompanyDescription: requireContextString(
        cumulativeContext.client_company_description,
        "client_company_description",
      ),
    });

    const parallelResult = await parallelRunner<Record<string, unknown>>({
      prompt,
      processor: payload.processor ?? DEFAULT_COMPANY_INTEL_BRIEFING_PROCESSOR,
      operationId: COMPANY_INTEL_BRIEFING_OPERATION_ID,
      providerAction: COMPANY_INTEL_BRIEFING_PROVIDER_ACTION,
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
      companyIndustry: getOptionalString(cumulativeContext.company_industry),
      companySize: getOptionalString(cumulativeContext.company_size),
      companyFunding: getOptionalString(cumulativeContext.company_funding),
      companyCompetitors: getOptionalCompetitors(cumulativeContext.company_competitors),
      clientCompanyName: requireContextString(
        cumulativeContext.client_company_name,
        "client_company_name",
      ),
      clientCompanyDomain: requireContextString(
        cumulativeContext.client_company_domain,
        "client_company_domain",
      ),
      clientCompanyDescription: requireContextString(
        cumulativeContext.client_company_description,
        "client_company_description",
      ),
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
          ? `Company intel briefing failed: ${error.message}`
          : `Company intel briefing failed: ${String(error)}`,
      failedOperationResult,
      errorDetails: {
        operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
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

  const persistenceOutcome = await persistCompanyIntelBriefingResults({
    client,
    payload,
    cumulativeContext,
    processor: String(
      operationResult.output?.processor ?? payload.processor ?? DEFAULT_COMPANY_INTEL_BRIEFING_PROCESSOR,
    ),
    parallelRunId: String(operationResult.output?.parallel_run_id),
    rawParallelOutput,
  });

  if (!persistenceOutcome.entityStateConfirmed || !persistenceOutcome.companyIntelBriefingConfirmed) {
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
      company_intel_briefing_id: persistenceOutcome.companyIntelBriefingId,
      last_operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
      error: message,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: persistenceOutcome.entityStateConfirmed,
        company_intel_briefing_confirmed: persistenceOutcome.companyIntelBriefingConfirmed,
      },
    };
  }

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    entity_id: persistenceOutcome.entityId,
    company_intel_briefing_id: persistenceOutcome.companyIntelBriefingId,
    last_operation_id: COMPANY_INTEL_BRIEFING_OPERATION_ID,
    executed_steps: executedSteps,
    persistence: {
      entity_state_confirmed: true,
      company_intel_briefing_confirmed: true,
    },
  };
}

export const __testables = {
  COMPANY_INTEL_BRIEFING_STEPS,
  validateWorkflowStepReferences,
  extractStructuredParallelOutput,
};
