import { logger } from "@trigger.dev/sdk/v3";

import { mergeStepOutput, WorkflowContext } from "./context.js";
import { createInternalApiClient, InternalApiClient } from "./internal-api.js";
import {
  markPipelineRunFailed,
  markPipelineRunRunning,
  markPipelineRunSucceeded,
  markStepResultFailed,
  markStepResultRunning,
  markStepResultSucceeded,
  recordStepTimelineEvent,
  WorkflowStepReference,
} from "./lineage.js";
import {
  executeOperation,
  isFailedOperationResult,
  OperationExecutionResult,
} from "./operations.js";

const ROOT_OPERATION_ID = "company.search.blitzapi";

interface RootWorkflowDefinitionStep {
  position: number;
  operationId: typeof ROOT_OPERATION_ID;
}

interface InternalStepResultRecord {
  id: string;
  step_position: number;
  status?: string;
  output_payload?: {
    cumulative_context?: WorkflowContext;
    [key: string]: unknown;
  } | null;
}

interface InternalPipelineRunRecord {
  id: string;
  submission_id: string;
  status?: "queued" | "running" | "succeeded" | "failed" | "canceled";
  error_message?: string | null;
  parent_pipeline_run_id?: string | null;
  blueprint_snapshot?: {
    entity?: {
      entity_type?: string;
      input?: WorkflowContext;
    };
    [key: string]: unknown;
  } | null;
  step_results: InternalStepResultRecord[];
}

interface ChildRunReference {
  pipeline_run_id: string;
  pipeline_run_status: string;
  trigger_run_id?: string | null;
  entity_type?: string | null;
  entity_input?: WorkflowContext | null;
}

interface ChildRunCreationResult {
  parent_pipeline_run_id: string;
  child_runs: ChildRunReference[];
  child_run_ids: string[];
  skipped_duplicates_count?: number;
  skipped_duplicate_identifiers?: string[];
}

interface TamCompanyLineage {
  company_identity: string;
  company_domain?: string;
  company_linkedin_url?: string;
  company_name?: string;
  company_enrichment_pipeline_run_id?: string;
  company_enrichment_status?: string;
  company_enrichment_error?: string | null;
  person_search_pipeline_run_id?: string;
  person_search_status?: string;
  person_search_error?: string | null;
}

interface TamBuildSummary {
  pages_processed: number;
  companies_discovered: number;
  company_runs_created: number;
  company_runs_succeeded: number;
  company_runs_failed: number;
  company_runs_skipped_duplicates: number;
  person_runs_created: number;
  person_runs_succeeded: number;
  person_runs_failed: number;
}

export interface TamBuildingWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  submission_id?: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;
  search_page_size?: number;
  company_batch_size?: number;
  poll_interval_ms?: number;
  person_max_people?: number;
  per_person_concurrency?: number;
  include_work_history?: boolean;
  api_url?: string;
  internal_api_key?: string;
}

export interface TamBuildingWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  failed_step_position?: number;
  error?: string;
  executed_steps: Array<{
    step_position: number;
    operation_id: typeof ROOT_OPERATION_ID;
    status: "succeeded" | "failed";
    operation_status: string;
  }>;
  summary: TamBuildSummary;
  company_results: TamCompanyLineage[];
}

export interface TamBuildingWorkflowDependencies {
  client?: InternalApiClient;
  sleep?: (ms: number) => Promise<void>;
}

const ROOT_STEPS: RootWorkflowDefinitionStep[] = [{ position: 1, operationId: ROOT_OPERATION_ID }];

const COMPANY_CHILD_STEPS = [
  { position: 1, operation_id: "company.enrich.profile", step_config: {} },
  { position: 2, operation_id: "company.research.infer_linkedin_url", step_config: {} },
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isInternalPipelineRunRecord(value: unknown): value is InternalPipelineRunRecord {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.submission_id === "string" &&
    Array.isArray(value.step_results)
  );
}

function isChildRunCreationResult(value: unknown): value is ChildRunCreationResult {
  return (
    isRecord(value) &&
    typeof value.parent_pipeline_run_id === "string" &&
    Array.isArray(value.child_runs) &&
    Array.isArray(value.child_run_ids)
  );
}

function toBoundedInteger(
  value: number | undefined,
  defaults: { fallback: number; min: number; max: number },
): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return defaults.fallback;
  }
  return Math.min(Math.max(Math.trunc(value), defaults.min), defaults.max);
}

function getClient(
  payload: TamBuildingWorkflowPayload,
  dependencies: TamBuildingWorkflowDependencies,
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

function validateWorkflowStepReferences(stepResults: WorkflowStepReference[]): void {
  const expectedPositions = ROOT_STEPS.map((step) => step.position);
  const actualPositions = stepResults.map((step) => step.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `TAM building workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  if (actualPositions[0] !== expectedPositions[0]) {
    throw new Error(`TAM building workflow step_results must match positions ${expectedPositions.join(", ")}`);
  }
}

function getStepReference(stepResults: WorkflowStepReference[], position: number): WorkflowStepReference {
  const stepReference = stepResults.find((candidate) => candidate.step_position === position);
  if (!stepReference) {
    throw new Error(`Missing step_result mapping for position ${position}`);
  }
  return stepReference;
}

function buildOperationResult(params: {
  pipelineRunId: string;
  status: string;
  output: Record<string, unknown>;
}): OperationExecutionResult {
  return {
    run_id: `${params.pipelineRunId}:${ROOT_OPERATION_ID}`,
    operation_id: ROOT_OPERATION_ID,
    status: params.status,
    output: params.output,
    provider_attempts: [],
  };
}

function normalizeOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : undefined;
}

function companyIdentity(context: WorkflowContext): string {
  return (
    normalizeOptionalString(context.company_domain) ??
    normalizeOptionalString(context.canonical_domain) ??
    normalizeOptionalString(context.domain) ??
    normalizeOptionalString(context.company_linkedin_url) ??
    normalizeOptionalString(context.company_name) ??
    `company:${JSON.stringify(context)}`
  );
}

function dedupeCompanies(results: WorkflowContext[]): WorkflowContext[] {
  const seen = new Set<string>();
  const deduped: WorkflowContext[] = [];

  for (const candidate of results) {
    const identity = companyIdentity(candidate);
    if (seen.has(identity)) {
      continue;
    }
    seen.add(identity);
    deduped.push(candidate);
  }

  return deduped;
}

function chunk<TValue>(items: TValue[], size: number): TValue[][] {
  const batches: TValue[][] = [];
  for (let index = 0; index < items.length; index += size) {
    batches.push(items.slice(index, index + size));
  }
  return batches;
}

async function runWithConcurrencyLimit<TInput, TOutput>(
  items: TInput[],
  concurrency: number,
  worker: (item: TInput, index: number) => Promise<TOutput>,
): Promise<TOutput[]> {
  const results = new Array<TOutput>(items.length);
  let nextIndex = 0;

  const runners = Array.from({ length: Math.min(items.length, concurrency) }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await worker(items[currentIndex] as TInput, currentIndex);
    }
  });

  await Promise.all(runners);
  return results;
}

function extractFinalContext(run: InternalPipelineRunRecord): WorkflowContext {
  const sortedResults = [...run.step_results].sort((left, right) => right.step_position - left.step_position);
  for (const stepResult of sortedResults) {
    const context = stepResult.output_payload?.cumulative_context;
    if (isRecord(context)) {
      return context;
    }
  }
  return {};
}

async function fetchPipelineRun(
  client: InternalApiClient,
  pipelineRunId: string,
): Promise<InternalPipelineRunRecord> {
  return client.post<InternalPipelineRunRecord>(
    "/api/internal/pipeline-runs/get",
    { pipeline_run_id: pipelineRunId },
    {
      validate: (data) => isInternalPipelineRunRecord(data) && data.id === pipelineRunId,
      validationErrorMessage: `Invalid pipeline run payload for ${pipelineRunId}`,
    },
  );
}

async function createChildRuns(
  client: InternalApiClient,
  payload: {
    parent_pipeline_run_id: string;
    submission_id: string;
    org_id: string;
    company_id: string;
    blueprint_snapshot: Record<string, unknown>;
    child_entities: WorkflowContext[];
    start_from_position: number;
    parent_cumulative_context?: WorkflowContext;
  },
): Promise<ChildRunCreationResult> {
  return client.post<ChildRunCreationResult>("/api/internal/pipeline-runs/create-children", payload, {
    validate: isChildRunCreationResult,
    validationErrorMessage: `Invalid child pipeline creation payload for ${payload.parent_pipeline_run_id}`,
  });
}

async function syncSubmissionStatus(client: InternalApiClient, submissionId: string): Promise<void> {
  await client.post("/api/internal/submissions/sync-status", { submission_id: submissionId });
}

function buildCompanyChildSnapshot(): Record<string, unknown> {
  return {
    blueprint: {
      name: "Dedicated TAM Company Enrichment",
      entity_type: "company",
    },
    steps: COMPANY_CHILD_STEPS.map((step) => ({ ...step })),
  };
}

function buildPersonChildSnapshot(payload: TamBuildingWorkflowPayload): Record<string, unknown> {
  const firstStepConfig: Record<string, unknown> = {};
  if (typeof payload.person_max_people === "number") {
    firstStepConfig.max_results = payload.person_max_people;
  }

  const secondStepConfig: Record<string, unknown> = {};
  if (payload.include_work_history === true) {
    secondStepConfig.include_work_history = true;
  }

  return {
    blueprint: {
      name: "Dedicated TAM Person Search Enrichment",
      entity_type: "company",
    },
    steps: [
      {
        position: 1,
        operation_id: "person.search",
        step_config: firstStepConfig,
      },
      {
        position: 2,
        operation_id: "person.enrich.profile",
        step_config: secondStepConfig,
      },
      {
        position: 3,
        operation_id: "person.contact.resolve_email",
        step_config: {},
      },
    ],
  };
}

function isTerminalPipelineStatus(
  status: InternalPipelineRunRecord["status"],
): status is "succeeded" | "failed" | "canceled" {
  return status === "succeeded" || status === "failed" || status === "canceled";
}

async function waitForPipelineRunTerminal(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  pollIntervalMs: number;
  sleep: (ms: number) => Promise<void>;
}): Promise<InternalPipelineRunRecord> {
  while (true) {
    const run = await fetchPipelineRun(params.client, params.pipelineRunId);
    if (isTerminalPipelineStatus(run.status)) {
      return run;
    }
    await params.sleep(params.pollIntervalMs);
  }
}

async function emitRootStepTimelineEvent(
  client: InternalApiClient,
  payload: TamBuildingWorkflowPayload,
  stepResultId: string,
  cumulativeContext: WorkflowContext,
  stepStatus: "succeeded" | "failed",
  operationResult: OperationExecutionResult,
  errorMessage?: string,
  errorDetails?: Record<string, unknown>,
): Promise<void> {
  if (!payload.submission_id) {
    return;
  }

  try {
    await recordStepTimelineEvent(client, {
      orgId: payload.org_id,
      companyId: payload.company_id,
      submissionId: payload.submission_id,
      pipelineRunId: payload.pipeline_run_id,
      entityType: "company",
      cumulativeContext,
      stepResultId,
      stepPosition: 1,
      operationId: ROOT_OPERATION_ID,
      stepStatus,
      errorMessage: errorMessage ?? null,
      errorDetails: errorDetails ?? null,
      operationResult: operationResult as unknown as Record<string, unknown>,
    });
  } catch (error) {
    logger.warn("tam-building timeline event failed", {
      pipeline_run_id: payload.pipeline_run_id,
      step_result_id: stepResultId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

export async function runTamBuildingWorkflow(
  payload: TamBuildingWorkflowPayload,
  dependencies: TamBuildingWorkflowDependencies = {},
): Promise<TamBuildingWorkflowResult> {
  const client = getClient(payload, dependencies);
  const sleep = dependencies.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms)));
  const searchPageSize = toBoundedInteger(payload.search_page_size, {
    fallback: 50,
    min: 1,
    max: 50,
  });
  const companyBatchSize = toBoundedInteger(payload.company_batch_size, {
    fallback: 25,
    min: 1,
    max: 100,
  });
  const pollIntervalMs = toBoundedInteger(payload.poll_interval_ms, {
    fallback: 2_000,
    min: 50,
    max: 30_000,
  });
  const perPersonConcurrency = toBoundedInteger(payload.per_person_concurrency, {
    fallback: 4,
    min: 1,
    max: 12,
  });

  validateWorkflowStepReferences(payload.step_results);

  const rootStepReference = getStepReference(payload.step_results, 1);
  const executedSteps: TamBuildingWorkflowResult["executed_steps"] = [];
  const companyResults: TamCompanyLineage[] = [];
  const summary: TamBuildSummary = {
    pages_processed: 0,
    companies_discovered: 0,
    company_runs_created: 0,
    company_runs_succeeded: 0,
    company_runs_failed: 0,
    company_runs_skipped_duplicates: 0,
    person_runs_created: 0,
    person_runs_succeeded: 0,
    person_runs_failed: 0,
  };
  let cumulativeContext = mergeStepOutput({}, payload.initial_context ?? {});

  await markPipelineRunRunning(client, payload.pipeline_run_id);
  await markStepResultRunning(client, {
    stepResultId: rootStepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  logger.info("tam-building workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    submission_id: payload.submission_id,
    search_page_size: searchPageSize,
    company_batch_size: companyBatchSize,
    poll_interval_ms: pollIntervalMs,
  });

  const discoveredCompanies: WorkflowContext[] = [];
  let cursor: string | undefined;

  try {
    do {
      const pageInput = {
        ...cumulativeContext,
        max_results: searchPageSize,
        ...(cursor ? { cursor } : {}),
      };
      const result = await executeOperation(client, {
        operationId: ROOT_OPERATION_ID,
        entityType: "company",
        input: pageInput,
      });

      summary.pages_processed += 1;

      if (isFailedOperationResult(result)) {
        throw new Error(`Operation failed: ${ROOT_OPERATION_ID}`);
      }

      const output = isRecord(result.output) ? result.output : {};
      const rawResults = Array.isArray(output.results) ? output.results : [];
      const typedResults = Array.isArray(output.results)
        ? output.results.filter((row): row is WorkflowContext => isRecord(row))
        : [];
      if (rawResults.length !== typedResults.length) {
        logger.warn("tam-building discarded non-object company search rows", {
          pipeline_run_id: payload.pipeline_run_id,
          discarded_count: rawResults.length - typedResults.length,
        });
      }

      discoveredCompanies.push(...typedResults);
      cursor = normalizeOptionalString(output.cursor);
    } while (cursor);
  } catch (error) {
    const message =
      error instanceof Error
        ? `TAM pagination failed: ${error.message}`
        : `TAM pagination failed: ${String(error)}`;
    const failedOutput = {
      tam_build: {
        summary,
        company_results: companyResults,
      },
    };
    const operationResult = buildOperationResult({
      pipelineRunId: payload.pipeline_run_id,
      status: "failed",
      output: failedOutput,
    });
    cumulativeContext = mergeStepOutput(cumulativeContext, failedOutput);

    await markStepResultFailed(client, {
      stepResultId: rootStepReference.step_result_id,
      inputPayload: payload.initial_context ?? {},
      operationResult,
      cumulativeContext,
      errorMessage: message,
      errorDetails: { pages_processed: summary.pages_processed },
    });
    await emitRootStepTimelineEvent(
      client,
      payload,
      rootStepReference.step_result_id,
      cumulativeContext,
      "failed",
      operationResult,
      message,
      { pages_processed: summary.pages_processed },
    );
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: { pages_processed: summary.pages_processed },
    });
    if (payload.submission_id) {
      await syncSubmissionStatus(client, payload.submission_id);
    }

    executedSteps.push({
      step_position: 1,
      operation_id: ROOT_OPERATION_ID,
      status: "failed",
      operation_status: "failed",
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      failed_step_position: 1,
      error: message,
      executed_steps: executedSteps,
      summary,
      company_results: companyResults,
    };
  }

  const uniqueCompanies = dedupeCompanies(discoveredCompanies);
  summary.companies_discovered = uniqueCompanies.length;

  if (uniqueCompanies.length > 0 && !payload.submission_id) {
    const message = "TAM building workflow requires submission_id to create downstream child pipeline runs";
    const operationResult = buildOperationResult({
      pipelineRunId: payload.pipeline_run_id,
      status: "failed",
      output: {
        tam_build: {
          summary,
          company_results: companyResults,
        },
      },
    });
    cumulativeContext = mergeStepOutput(cumulativeContext, {
      tam_build: {
        summary,
        company_results: companyResults,
      },
    });

    await markStepResultFailed(client, {
      stepResultId: rootStepReference.step_result_id,
      inputPayload: payload.initial_context ?? {},
      operationResult,
      cumulativeContext,
      errorMessage: message,
      errorDetails: {},
    });
    await emitRootStepTimelineEvent(
      client,
      payload,
      rootStepReference.step_result_id,
      cumulativeContext,
      "failed",
      operationResult,
      message,
      {},
    );
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {},
    });

    executedSteps.push({
      step_position: 1,
      operation_id: ROOT_OPERATION_ID,
      status: "failed",
      operation_status: "failed",
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      failed_step_position: 1,
      error: message,
      executed_steps: executedSteps,
      summary,
      company_results: companyResults,
    };
  }

  const companyBatches = chunk(uniqueCompanies, companyBatchSize);

  for (const batch of companyBatches) {
    const childCreation = await createChildRuns(client, {
      parent_pipeline_run_id: payload.pipeline_run_id,
      submission_id: payload.submission_id as string,
      org_id: payload.org_id,
      company_id: payload.company_id,
      blueprint_snapshot: buildCompanyChildSnapshot(),
      child_entities: batch.map((company) => ({
        entity_type: "company",
        ...company,
      })),
      start_from_position: 1,
    });

    summary.company_runs_created += childCreation.child_runs.length;
    summary.company_runs_skipped_duplicates += childCreation.skipped_duplicates_count ?? 0;

    const terminalCompanyRuns = await runWithConcurrencyLimit(
      childCreation.child_runs,
      Math.min(companyBatchSize, 12),
      async (childRun) =>
        waitForPipelineRunTerminal({
          client,
          pipelineRunId: childRun.pipeline_run_id,
          pollIntervalMs,
          sleep,
        }),
    );

    const successfulCompanyRuns = terminalCompanyRuns.filter((run) => run.status === "succeeded");

    for (const terminalRun of terminalCompanyRuns) {
      const finalContext = extractFinalContext(terminalRun);
      companyResults.push({
        company_identity: companyIdentity(finalContext),
        company_domain:
          normalizeOptionalString(finalContext.company_domain) ??
          normalizeOptionalString(finalContext.canonical_domain) ??
          normalizeOptionalString(finalContext.domain),
        company_linkedin_url: normalizeOptionalString(finalContext.company_linkedin_url),
        company_name: normalizeOptionalString(finalContext.company_name),
        company_enrichment_pipeline_run_id: terminalRun.id,
        company_enrichment_status: terminalRun.status ?? "unknown",
        company_enrichment_error: terminalRun.error_message ?? null,
      });

      if (terminalRun.status === "succeeded") {
        summary.company_runs_succeeded += 1;
      } else {
        summary.company_runs_failed += 1;
      }
    }

    const personRuns = await runWithConcurrencyLimit(
      successfulCompanyRuns,
      Math.min(perPersonConcurrency, 12),
      async (companyRun) => {
        const finalContext = extractFinalContext(companyRun);
        const creationResult = await createChildRuns(client, {
          parent_pipeline_run_id: companyRun.id,
          submission_id: companyRun.submission_id,
          org_id: payload.org_id,
          company_id: payload.company_id,
          blueprint_snapshot: buildPersonChildSnapshot(payload),
          child_entities: [
            {
              entity_type: "company",
              company_domain:
                normalizeOptionalString(finalContext.company_domain) ??
                normalizeOptionalString(finalContext.canonical_domain) ??
                normalizeOptionalString(finalContext.domain),
            },
          ],
          start_from_position: 1,
          parent_cumulative_context: finalContext,
        });

        summary.person_runs_created += creationResult.child_runs.length;

        const personChild = creationResult.child_runs[0];
        if (!personChild) {
          return null;
        }

        return waitForPipelineRunTerminal({
          client,
          pipelineRunId: personChild.pipeline_run_id,
          pollIntervalMs,
          sleep,
        });
      },
    );

    for (const personRun of personRuns) {
      if (!personRun) {
        continue;
      }
      const finalContext = extractFinalContext(personRun);
      const identity = companyIdentity(finalContext);
      const companyResult = companyResults.find((candidate) => candidate.company_identity === identity);
      if (!companyResult) {
        continue;
      }

      companyResult.person_search_pipeline_run_id = personRun.id;
      companyResult.person_search_status = personRun.status ?? "unknown";
      companyResult.person_search_error = personRun.error_message ?? null;

      if (personRun.status === "succeeded") {
        summary.person_runs_succeeded += 1;
      } else {
        summary.person_runs_failed += 1;
      }
    }
  }

  const output = {
    tam_build: {
      summary,
      company_results: companyResults,
    },
  };
  cumulativeContext = mergeStepOutput(cumulativeContext, output);

  const hasFailures = summary.company_runs_failed > 0 || summary.person_runs_failed > 0;
  const operationResult = buildOperationResult({
    pipelineRunId: payload.pipeline_run_id,
    status: hasFailures ? "failed" : uniqueCompanies.length > 0 ? "found" : "not_found",
    output,
  });

  if (hasFailures) {
    const message = "TAM build completed with downstream workflow failures";
    await markStepResultFailed(client, {
      stepResultId: rootStepReference.step_result_id,
      inputPayload: payload.initial_context ?? {},
      operationResult,
      cumulativeContext,
      errorMessage: message,
      errorDetails: {
        company_runs_failed: summary.company_runs_failed,
        person_runs_failed: summary.person_runs_failed,
      },
    });
    await emitRootStepTimelineEvent(
      client,
      payload,
      rootStepReference.step_result_id,
      cumulativeContext,
      "failed",
      operationResult,
      message,
      {
        company_runs_failed: summary.company_runs_failed,
        person_runs_failed: summary.person_runs_failed,
      },
    );
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        company_runs_failed: summary.company_runs_failed,
        person_runs_failed: summary.person_runs_failed,
      },
    });
    if (payload.submission_id) {
      await syncSubmissionStatus(client, payload.submission_id);
    }

    executedSteps.push({
      step_position: 1,
      operation_id: ROOT_OPERATION_ID,
      status: "failed",
      operation_status: operationResult.status,
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      failed_step_position: 1,
      error: message,
      executed_steps: executedSteps,
      summary,
      company_results: companyResults,
    };
  }

  await markStepResultSucceeded(client, {
    stepResultId: rootStepReference.step_result_id,
    operationResult,
    cumulativeContext,
  });
  await emitRootStepTimelineEvent(
    client,
    payload,
    rootStepReference.step_result_id,
    cumulativeContext,
    "succeeded",
    operationResult,
  );
  await markPipelineRunSucceeded(client, payload.pipeline_run_id);
  if (payload.submission_id) {
    await syncSubmissionStatus(client, payload.submission_id);
  }

  executedSteps.push({
    step_position: 1,
    operation_id: ROOT_OPERATION_ID,
    status: "succeeded",
    operation_status: operationResult.status,
  });

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    executed_steps: executedSteps,
    summary,
    company_results: companyResults,
  };
}

export const __testables = {
  ROOT_STEPS,
  validateWorkflowStepReferences,
  dedupeCompanies,
  buildCompanyChildSnapshot,
  buildPersonChildSnapshot,
  companyIdentity,
};
