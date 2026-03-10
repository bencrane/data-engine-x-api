import { logger } from "@trigger.dev/sdk/v3";

import { buildPersistablePersonContext, mergeStepOutput, normalizeCompanyDomain, WorkflowContext } from "./context.js";
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
import { renderPersonIntelBriefingPrompt } from "./prompts/person-intel-briefing.js";

type PersonIntelBriefingWorkflowOperationId = "person.derive.intel_briefing";

const PERSON_INTEL_BRIEFING_OPERATION_ID: PersonIntelBriefingWorkflowOperationId =
  "person.derive.intel_briefing";
const PERSON_INTEL_BRIEFING_PROVIDER_ACTION = "deep_research_person_intel_briefing";
const DEFAULT_PERSON_INTEL_BRIEFING_PROCESSOR = "pro";

interface PersonIntelBriefingWorkflowDefinitionStep {
  position: number;
  operationId: PersonIntelBriefingWorkflowOperationId;
}

interface PersonIntelBriefingDedicatedWriteResult {
  id?: string;
  person_full_name: string;
  person_linkedin_url?: string | null;
  client_company_name?: string | null;
  [key: string]: unknown;
}

interface PersistenceOutcome {
  entityStateConfirmed: boolean;
  entityId?: string;
  personIntelBriefingConfirmed: boolean;
  personIntelBriefingId?: string;
  errors: string[];
  errorDetails: Record<string, unknown>;
}

export interface PersonIntelBriefingWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  person_full_name: string;
  person_linkedin_url?: string;
  person_current_job_title?: string;
  person_current_company_name: string;
  person_current_company_domain?: string;
  person_current_company_description?: string;
  client_company_name: string;
  client_company_domain: string;
  client_company_description: string;
  customer_company_name?: string;
  customer_company_domain?: string;
  step_results: WorkflowStepReference[];
  submission_id?: string;
  initial_context?: WorkflowContext;
  processor?: string;
  api_url?: string;
  internal_api_key?: string;
}

export interface PersonIntelBriefingWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  entity_id?: string;
  person_intel_briefing_id?: string;
  last_operation_id?: PersonIntelBriefingWorkflowOperationId | null;
  error?: string;
  executed_steps: Array<{
    step_position: number;
    operation_id: PersonIntelBriefingWorkflowOperationId;
    status: "succeeded";
    operation_status?: string;
  }>;
  persistence: {
    entity_state_confirmed: boolean;
    person_intel_briefing_confirmed: boolean;
  };
}

export type ParallelDeepResearchRunner = <TExtracted>(
  params: ParallelDeepResearchParams<TExtracted>,
) => Promise<ParallelDeepResearchSuccess<TExtracted>>;

export interface PersonIntelBriefingWorkflowDependencies {
  client?: InternalApiClient;
  parallelFetchImpl?: typeof fetch;
  parallelSleep?: SleepFn;
  parallelApiKey?: string;
  parallelRunner?: ParallelDeepResearchRunner;
}

const PERSON_INTEL_BRIEFING_STEPS: PersonIntelBriefingWorkflowDefinitionStep[] = [
  {
    position: 1,
    operationId: PERSON_INTEL_BRIEFING_OPERATION_ID,
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

function normalizeOptionalLinkedinUrl(value: unknown): string | undefined {
  const normalized = getOptionalString(value);
  return normalized ? normalized.replace(/\/+$/, "").toLowerCase() : undefined;
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
  const expectedPositions = PERSON_INTEL_BRIEFING_STEPS.map((step) => step.position).sort(
    (a, b) => a - b,
  );
  const actualPositions = stepResults.map((step) => step.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `Person intel briefing workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  for (let index = 0; index < expectedPositions.length; index += 1) {
    if (expectedPositions[index] !== actualPositions[index]) {
      throw new Error(
        `Person intel briefing workflow step_results must match positions ${expectedPositions.join(", ")}`,
      );
    }
  }
}

function getClient(
  payload: PersonIntelBriefingWorkflowPayload,
  dependencies: PersonIntelBriefingWorkflowDependencies,
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
  dependencies: PersonIntelBriefingWorkflowDependencies,
): ParallelDeepResearchRunner {
  return dependencies.parallelRunner ?? runParallelDeepResearch;
}

function buildInitialContext(payload: PersonIntelBriefingWorkflowPayload): WorkflowContext {
  const merged = mergeStepOutput(payload.initial_context ?? {}, {
    person_full_name: requireContextString(payload.person_full_name, "person_full_name"),
    full_name: requireContextString(payload.person_full_name, "person_full_name"),
    person_current_company_name: requireContextString(
      payload.person_current_company_name,
      "person_current_company_name",
    ),
    current_company_name: requireContextString(
      payload.person_current_company_name,
      "person_current_company_name",
    ),
    client_company_name: requireContextString(payload.client_company_name, "client_company_name"),
    client_company_domain: normalizeCompanyDomain(
      requireContextString(payload.client_company_domain, "client_company_domain"),
    ),
    client_company_description: requireContextString(
      payload.client_company_description,
      "client_company_description",
    ),
    ...(getOptionalString(payload.person_linkedin_url)
      ? {
          person_linkedin_url: getOptionalString(payload.person_linkedin_url),
          linkedin_url: getOptionalString(payload.person_linkedin_url),
        }
      : {}),
    ...(getOptionalString(payload.person_current_job_title)
      ? {
          person_current_job_title: getOptionalString(payload.person_current_job_title),
          title: getOptionalString(payload.person_current_job_title),
          current_title: getOptionalString(payload.person_current_job_title),
        }
      : {}),
    ...(getOptionalString(payload.person_current_company_domain)
      ? {
          person_current_company_domain: getOptionalString(payload.person_current_company_domain),
          current_company_domain: getOptionalString(payload.person_current_company_domain),
        }
      : {}),
    ...(getOptionalString(payload.person_current_company_description)
      ? {
          person_current_company_description: getOptionalString(payload.person_current_company_description),
          current_company_description: getOptionalString(payload.person_current_company_description),
        }
      : {}),
    ...(getOptionalString(payload.customer_company_name)
      ? { customer_company_name: getOptionalString(payload.customer_company_name) }
      : {}),
    ...(getOptionalString(payload.customer_company_domain)
      ? { customer_company_domain: getOptionalString(payload.customer_company_domain) }
      : {}),
  });

  const persisted = buildPersistablePersonContext(merged);
  if (!getOptionalString(persisted.linkedin_url) && !getOptionalString(persisted.title)) {
    throw new Error("person_linkedin_url or person_current_job_title is required");
  }

  return persisted;
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
  personFullName: string;
  personLinkedinUrl?: string;
  personCurrentJobTitle?: string;
  personCurrentCompanyName: string;
  personCurrentCompanyDomain?: string;
  personCurrentCompanyDescription?: string;
  clientCompanyName: string;
  clientCompanyDomain: string;
  clientCompanyDescription: string;
  customerCompanyName?: string;
  customerCompanyDomain?: string;
  processor: string;
  parallelRunId: string;
  parallelRawResponse: Record<string, unknown>;
  rawParallelOutput: Record<string, unknown>;
}): WorkflowContext {
  return buildPersistablePersonContext({
    person_full_name: params.personFullName,
    full_name: params.personFullName,
    ...(params.personLinkedinUrl
      ? {
          person_linkedin_url: params.personLinkedinUrl,
          linkedin_url: params.personLinkedinUrl,
        }
      : {}),
    ...(params.personCurrentJobTitle
      ? {
          person_current_job_title: params.personCurrentJobTitle,
          person_current_title: params.personCurrentJobTitle,
          title: params.personCurrentJobTitle,
          current_title: params.personCurrentJobTitle,
        }
      : {}),
    person_current_company_name: params.personCurrentCompanyName,
    current_company_name: params.personCurrentCompanyName,
    ...(params.personCurrentCompanyDomain
      ? {
          person_current_company_domain: params.personCurrentCompanyDomain,
          current_company_domain: params.personCurrentCompanyDomain,
        }
      : {}),
    ...(params.personCurrentCompanyDescription
      ? {
          person_current_company_description: params.personCurrentCompanyDescription,
          current_company_description: params.personCurrentCompanyDescription,
        }
      : {}),
    client_company_name: params.clientCompanyName,
    client_company_domain: params.clientCompanyDomain,
    client_company_description: params.clientCompanyDescription,
    ...(params.customerCompanyName ? { customer_company_name: params.customerCompanyName } : {}),
    ...(params.customerCompanyDomain ? { customer_company_domain: params.customerCompanyDomain } : {}),
    parallel_run_id: params.parallelRunId,
    processor: params.processor,
    parallel_raw_response: params.parallelRawResponse,
    raw_parallel_output: params.rawParallelOutput,
  });
}

function buildSuccessfulOperationResult(params: {
  personFullName: string;
  personLinkedinUrl?: string;
  personCurrentJobTitle?: string;
  personCurrentCompanyName: string;
  personCurrentCompanyDomain?: string;
  personCurrentCompanyDescription?: string;
  clientCompanyName: string;
  clientCompanyDomain: string;
  clientCompanyDescription: string;
  customerCompanyName?: string;
  customerCompanyDomain?: string;
  processor: string;
  parallelRunId: string;
  pollCount: number;
  elapsedMs: number;
  parallelRawResponse: Record<string, unknown>;
  rawParallelOutput: Record<string, unknown>;
}): OperationExecutionResult {
  return {
    run_id: params.parallelRunId,
    operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
    status: "found",
    output: buildWorkflowOutput(params),
    provider_attempts: [
      {
        provider: "parallel",
        action: PERSON_INTEL_BRIEFING_PROVIDER_ACTION,
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
      action: PERSON_INTEL_BRIEFING_PROVIDER_ACTION,
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
      run_id: error.parallelRunId ?? `${PERSON_INTEL_BRIEFING_OPERATION_ID}:failed`,
      operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
      status: "failed",
      output: {
        person_full_name: context.person_full_name,
        person_linkedin_url: context.person_linkedin_url ?? context.linkedin_url,
        person_current_company_name: context.person_current_company_name ?? context.current_company_name,
        client_company_name: context.client_company_name,
        parallel_run_id: error.parallelRunId ?? undefined,
      },
      provider_attempts: [providerAttempt],
    };
  }

  return {
    run_id: `${PERSON_INTEL_BRIEFING_OPERATION_ID}:failed`,
    operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
    status: "failed",
    output: {
      person_full_name: context.person_full_name,
      person_linkedin_url: context.person_linkedin_url ?? context.linkedin_url,
      person_current_company_name: context.person_current_company_name ?? context.current_company_name,
      client_company_name: context.client_company_name,
    },
    provider_attempts: [
      {
        provider: "parallel",
        action: PERSON_INTEL_BRIEFING_PROVIDER_ACTION,
        status: "failed",
        error: error instanceof Error ? error.message : String(error),
      },
    ],
  };
}

async function writePersonIntelBriefingConfirmed(
  client: InternalApiClient,
  params: {
    personFullName: string;
    personLinkedinUrl?: string;
    personCurrentCompanyName: string;
    personCurrentCompanyDomain?: string;
    personCurrentJobTitle?: string;
    clientCompanyName: string;
    clientCompanyDescription: string;
    customerCompanyName?: string;
    customerCompanyDomain?: string;
    rawParallelOutput: Record<string, unknown>;
    parallelRunId: string;
    processor: string;
    submissionId?: string;
    pipelineRunId: string;
  },
): Promise<PersonIntelBriefingDedicatedWriteResult> {
  const normalizedLinkedinUrl = normalizeOptionalLinkedinUrl(params.personLinkedinUrl);
  const normalizedCurrentCompanyDomain = getOptionalString(params.personCurrentCompanyDomain)
    ? normalizeCompanyDomain(params.personCurrentCompanyDomain as string)
    : undefined;

  return writeDedicatedTableConfirmed<PersonIntelBriefingDedicatedWriteResult>(client, {
    path: "/api/internal/person-intel-briefings/upsert",
    payload: {
      person_full_name: params.personFullName,
      person_linkedin_url: normalizedLinkedinUrl,
      person_current_company_name: params.personCurrentCompanyName,
      person_current_company_domain: normalizedCurrentCompanyDomain,
      person_current_job_title: params.personCurrentJobTitle,
      client_company_name: params.clientCompanyName,
      // The current FastAPI request model omits client_company_domain, so this write
      // stays within the existing endpoint contract even though the table has the column.
      client_company_description: params.clientCompanyDescription,
      customer_company_name: params.customerCompanyName,
      customer_company_domain: params.customerCompanyDomain,
      raw_parallel_output: params.rawParallelOutput,
      parallel_run_id: params.parallelRunId,
      processor: params.processor,
      source_submission_id: params.submissionId,
      source_pipeline_run_id: params.pipelineRunId,
    },
    validate: (response) =>
      isRecord(response) &&
      response.person_full_name === params.personFullName &&
      (response.client_company_name == null || response.client_company_name === params.clientCompanyName) &&
      (normalizedLinkedinUrl === undefined || response.person_linkedin_url === normalizedLinkedinUrl),
    confirmationErrorMessage: "Person intel briefing dedicated-table write could not be confirmed",
  });
}

async function failWorkflow(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  stepReference?: WorkflowStepReference;
  cumulativeContext: WorkflowContext;
  executedSteps: PersonIntelBriefingWorkflowResult["executed_steps"];
  message: string;
  failedOperationResult?: OperationExecutionResult;
  errorDetails?: Record<string, unknown>;
  persistence?: PersonIntelBriefingWorkflowResult["persistence"];
}): Promise<PersonIntelBriefingWorkflowResult> {
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
        person_intel_briefing_confirmed: false,
      },
  };
}

async function persistPersonIntelBriefingResults(params: {
  client: InternalApiClient;
  payload: PersonIntelBriefingWorkflowPayload;
  cumulativeContext: WorkflowContext;
  processor: string;
  parallelRunId: string;
  rawParallelOutput: Record<string, unknown>;
}): Promise<PersistenceOutcome> {
  const outcome: PersistenceOutcome = {
    entityStateConfirmed: false,
    personIntelBriefingConfirmed: false,
    errors: [],
    errorDetails: {},
  };

  try {
    const entityState: EntityStateUpsertResult = await upsertEntityStateConfirmed(params.client, {
      pipelineRunId: params.payload.pipeline_run_id,
      entityType: "person",
      cumulativeContext: params.cumulativeContext,
      lastOperationId: PERSON_INTEL_BRIEFING_OPERATION_ID,
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
    const personIntelBriefingRow = await writePersonIntelBriefingConfirmed(params.client, {
      personFullName: requireContextString(params.cumulativeContext.person_full_name, "person_full_name"),
      personLinkedinUrl: getOptionalString(
        params.cumulativeContext.person_linkedin_url ?? params.cumulativeContext.linkedin_url,
      ),
      personCurrentCompanyName: requireContextString(
        params.cumulativeContext.person_current_company_name ?? params.cumulativeContext.current_company_name,
        "person_current_company_name",
      ),
      personCurrentCompanyDomain: getOptionalString(
        params.cumulativeContext.person_current_company_domain ?? params.cumulativeContext.current_company_domain,
      ),
      personCurrentJobTitle: getOptionalString(
        params.cumulativeContext.person_current_job_title ??
          params.cumulativeContext.person_current_title ??
          params.cumulativeContext.title,
      ),
      clientCompanyName: requireContextString(
        params.cumulativeContext.client_company_name,
        "client_company_name",
      ),
      clientCompanyDescription: requireContextString(
        params.cumulativeContext.client_company_description,
        "client_company_description",
      ),
      customerCompanyName: getOptionalString(params.cumulativeContext.customer_company_name),
      customerCompanyDomain: getOptionalString(params.cumulativeContext.customer_company_domain),
      rawParallelOutput: params.rawParallelOutput,
      parallelRunId: params.parallelRunId,
      processor: params.processor,
      submissionId: params.payload.submission_id,
      pipelineRunId: params.payload.pipeline_run_id,
    });
    outcome.personIntelBriefingConfirmed = true;
    outcome.personIntelBriefingId = getOptionalString(personIntelBriefingRow.id);
  } catch (error) {
    outcome.errors.push(
      error instanceof Error
        ? `Person intel briefing upsert failed: ${error.message}`
        : `Person intel briefing upsert failed: ${String(error)}`,
    );
    outcome.errorDetails.person_intel_briefing = {
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
  if (outcome.personIntelBriefingConfirmed) {
    outcome.errorDetails.person_intel_briefing = {
      confirmed: true,
      id: outcome.personIntelBriefingId,
    };
  }

  return outcome;
}

export async function runPersonIntelBriefingWorkflow(
  payload: PersonIntelBriefingWorkflowPayload,
  dependencies: PersonIntelBriefingWorkflowDependencies = {},
): Promise<PersonIntelBriefingWorkflowResult> {
  const client = getClient(payload, dependencies);
  const parallelRunner = getParallelRunner(dependencies);
  const executedSteps: PersonIntelBriefingWorkflowResult["executed_steps"] = [];
  let cumulativeContext: WorkflowContext;

  try {
    cumulativeContext = buildInitialContext(payload);
  } catch (error) {
    const message =
      error instanceof Error
        ? `Invalid person intel briefing workflow input: ${error.message}`
        : `Invalid person intel briefing workflow input: ${String(error)}`;

    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
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
        person_intel_briefing_confirmed: false,
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
        : `Person intel briefing workflow validation failed: ${String(error)}`;

    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
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
        person_intel_briefing_confirmed: false,
      },
    };
  }

  const stepReferenceMap = getStepReferenceMap(payload.step_results);
  const step = PERSON_INTEL_BRIEFING_STEPS[0];
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

  logger.info("person-intel-briefing workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    person_full_name: cumulativeContext.person_full_name,
    person_linkedin_url: cumulativeContext.person_linkedin_url ?? cumulativeContext.linkedin_url,
    person_current_company_name:
      cumulativeContext.person_current_company_name ?? cumulativeContext.current_company_name,
    client_company_name: cumulativeContext.client_company_name,
    processor: payload.processor ?? DEFAULT_PERSON_INTEL_BRIEFING_PROCESSOR,
    polling_schedule_ms: DEFAULT_PARALLEL_POLLING_SCHEDULE_MS,
  });

  await markStepResultRunning(client, {
    stepResultId: stepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  let operationResult: OperationExecutionResult;
  let rawParallelOutput: Record<string, unknown>;

  try {
    const prompt = renderPersonIntelBriefingPrompt({
      personFullName: requireContextString(cumulativeContext.person_full_name, "person_full_name"),
      personLinkedinUrl: getOptionalString(
        cumulativeContext.person_linkedin_url ?? cumulativeContext.linkedin_url,
      ),
      personCurrentJobTitle: getOptionalString(
        cumulativeContext.person_current_job_title ??
          cumulativeContext.person_current_title ??
          cumulativeContext.title,
      ),
      personCurrentCompanyName: requireContextString(
        cumulativeContext.person_current_company_name ?? cumulativeContext.current_company_name,
        "person_current_company_name",
      ),
      personCurrentCompanyDomain: getOptionalString(
        cumulativeContext.person_current_company_domain ?? cumulativeContext.current_company_domain,
      ),
      personCurrentCompanyDescription: getOptionalString(
        cumulativeContext.person_current_company_description ??
          cumulativeContext.current_company_description,
      ),
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
      customerCompanyName: getOptionalString(cumulativeContext.customer_company_name),
      customerCompanyDomain: getOptionalString(cumulativeContext.customer_company_domain),
    });

    const parallelResult = await parallelRunner<Record<string, unknown>>({
      prompt,
      processor: payload.processor ?? DEFAULT_PERSON_INTEL_BRIEFING_PROCESSOR,
      operationId: PERSON_INTEL_BRIEFING_OPERATION_ID,
      providerAction: PERSON_INTEL_BRIEFING_PROVIDER_ACTION,
      apiKey: dependencies.parallelApiKey,
      fetchImpl: dependencies.parallelFetchImpl,
      sleep: dependencies.parallelSleep,
      extractOutput: (result) => extractStructuredParallelOutput(result),
    });

    rawParallelOutput = parallelResult.extractedOutput;
    operationResult = buildSuccessfulOperationResult({
      personFullName: requireContextString(cumulativeContext.person_full_name, "person_full_name"),
      personLinkedinUrl: getOptionalString(
        cumulativeContext.person_linkedin_url ?? cumulativeContext.linkedin_url,
      ),
      personCurrentJobTitle: getOptionalString(
        cumulativeContext.person_current_job_title ??
          cumulativeContext.person_current_title ??
          cumulativeContext.title,
      ),
      personCurrentCompanyName: requireContextString(
        cumulativeContext.person_current_company_name ?? cumulativeContext.current_company_name,
        "person_current_company_name",
      ),
      personCurrentCompanyDomain: getOptionalString(
        cumulativeContext.person_current_company_domain ?? cumulativeContext.current_company_domain,
      ),
      personCurrentCompanyDescription: getOptionalString(
        cumulativeContext.person_current_company_description ??
          cumulativeContext.current_company_description,
      ),
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
      customerCompanyName: getOptionalString(cumulativeContext.customer_company_name),
      customerCompanyDomain: getOptionalString(cumulativeContext.customer_company_domain),
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
          ? `Person intel briefing failed: ${error.message}`
          : `Person intel briefing failed: ${String(error)}`,
      failedOperationResult,
      errorDetails: {
        operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
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

  const persistenceOutcome = await persistPersonIntelBriefingResults({
    client,
    payload,
    cumulativeContext,
    processor: String(
      operationResult.output?.processor ?? payload.processor ?? DEFAULT_PERSON_INTEL_BRIEFING_PROCESSOR,
    ),
    parallelRunId: String(operationResult.output?.parallel_run_id),
    rawParallelOutput,
  });

  if (!persistenceOutcome.entityStateConfirmed || !persistenceOutcome.personIntelBriefingConfirmed) {
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
      person_intel_briefing_id: persistenceOutcome.personIntelBriefingId,
      last_operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
      error: message,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: persistenceOutcome.entityStateConfirmed,
        person_intel_briefing_confirmed: persistenceOutcome.personIntelBriefingConfirmed,
      },
    };
  }

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    entity_id: persistenceOutcome.entityId,
    person_intel_briefing_id: persistenceOutcome.personIntelBriefingId,
    last_operation_id: PERSON_INTEL_BRIEFING_OPERATION_ID,
    executed_steps: executedSteps,
    persistence: {
      entity_state_confirmed: true,
      person_intel_briefing_confirmed: true,
    },
  };
}

export const __testables = {
  PERSON_INTEL_BRIEFING_STEPS,
  validateWorkflowStepReferences,
  extractStructuredParallelOutput,
};
