import { logger } from "@trigger.dev/sdk/v3";

import {
  buildPersonCandidateContext,
  buildPersonSearchSeedContext,
  buildPersistablePersonContext,
  mergeStepOutput,
  WorkflowContext,
} from "./context.js";
import { createInternalApiClient, InternalApiClient } from "./internal-api.js";
import {
  markPipelineRunFailed,
  markPipelineRunRunning,
  markPipelineRunSucceeded,
  markStepResultFailed,
  markStepResultRunning,
  markStepResultSkipped,
  markStepResultSucceeded,
  recordStepTimelineEvent,
  WorkflowStepReference,
} from "./lineage.js";
import {
  executeOperation,
  isFailedOperationResult,
  OperationExecutionResult,
} from "./operations.js";
import { upsertEntityStateConfirmed } from "./persistence.js";

type PersonWorkflowOperationId =
  | "person.search"
  | "person.enrich.profile"
  | "person.contact.resolve_email";

interface PersonWorkflowDefinitionStep {
  position: number;
  operationId: PersonWorkflowOperationId;
}

interface PersonBatchOutcome {
  person_index: number;
  full_name?: string;
  linkedin_url?: string;
  work_email?: string;
  email_status?: string;
  entity_id?: string;
  persisted: boolean;
  last_operation_id: PersonWorkflowOperationId;
  profile_status: "found" | "not_found" | "failed";
  contact_status: "found" | "not_found" | "failed" | "not_attempted";
  errors: string[];
  context: WorkflowContext;
}

interface BatchSummary {
  processed_count: number;
  succeeded_count: number;
  failed_count: number;
  not_found_count: number;
  persisted_count?: number;
  persistence_failed_count?: number;
}

export interface PersonSearchEnrichmentWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  company_domain: string;
  submission_id?: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;
  max_people?: number;
  per_person_concurrency?: number;
  include_work_history?: boolean;
  api_url?: string;
  internal_api_key?: string;
}

export interface PersonSearchEnrichmentWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  failed_step_position?: number;
  error?: string;
  people_discovered: number;
  people_persisted: number;
  person_results: Array<Omit<PersonBatchOutcome, "context">>;
  executed_steps: Array<{
    step_position: number;
    operation_id: PersonWorkflowOperationId;
    status: "succeeded" | "skipped";
    operation_status?: string;
  }>;
}

export interface PersonSearchEnrichmentWorkflowDependencies {
  client?: InternalApiClient;
}

const PERSON_SEARCH_ENRICHMENT_STEPS: PersonWorkflowDefinitionStep[] = [
  { position: 1, operationId: "person.search" },
  { position: 2, operationId: "person.enrich.profile" },
  { position: 3, operationId: "person.contact.resolve_email" },
];

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
  const expectedPositions = PERSON_SEARCH_ENRICHMENT_STEPS.map((step) => step.position).sort(
    (a, b) => a - b,
  );
  const actualPositions = stepResults.map((step) => step.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `Person search enrichment workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  for (let index = 0; index < expectedPositions.length; index += 1) {
    if (expectedPositions[index] !== actualPositions[index]) {
      throw new Error(
        `Person search enrichment workflow step_results must match positions ${expectedPositions.join(", ")}`,
      );
    }
  }
}

function getClient(
  payload: PersonSearchEnrichmentWorkflowPayload,
  dependencies: PersonSearchEnrichmentWorkflowDependencies,
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

function toBoundedInteger(
  value: number | undefined,
  defaults: { fallback: number; min: number; max: number },
): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return defaults.fallback;
  }
  return Math.min(Math.max(Math.trunc(value), defaults.min), defaults.max);
}

function buildBatchOperationResult(params: {
  pipelineRunId: string;
  operationId: PersonWorkflowOperationId;
  output: Record<string, unknown>;
  status: "found" | "not_found";
}): OperationExecutionResult {
  return {
    run_id: `${params.pipelineRunId}:${params.operationId}`,
    operation_id: params.operationId,
    status: params.status,
    output: params.output,
    provider_attempts: [],
  };
}

function buildPersonOutcomeSummary(outcome: PersonBatchOutcome): Omit<PersonBatchOutcome, "context"> {
  return {
    person_index: outcome.person_index,
    full_name: typeof outcome.context.full_name === "string" ? outcome.context.full_name : undefined,
    linkedin_url:
      typeof outcome.context.linkedin_url === "string" ? outcome.context.linkedin_url : undefined,
    work_email: typeof outcome.context.work_email === "string" ? outcome.context.work_email : undefined,
    email_status:
      typeof outcome.context.email_status === "string" ? outcome.context.email_status : undefined,
    entity_id: outcome.entity_id,
    persisted: outcome.persisted,
    last_operation_id: outcome.last_operation_id,
    profile_status: outcome.profile_status,
    contact_status: outcome.contact_status,
    errors: outcome.errors,
  };
}

function buildPeopleListSummary(outcomes: PersonBatchOutcome[]): Array<Record<string, unknown>> {
  return outcomes.map((outcome) => ({
    person_index: outcome.person_index,
    full_name: typeof outcome.context.full_name === "string" ? outcome.context.full_name : null,
    linkedin_url: typeof outcome.context.linkedin_url === "string" ? outcome.context.linkedin_url : null,
    work_email: typeof outcome.context.work_email === "string" ? outcome.context.work_email : null,
    persisted: outcome.persisted,
    entity_id: outcome.entity_id ?? null,
    profile_status: outcome.profile_status,
    contact_status: outcome.contact_status,
    errors: outcome.errors,
  }));
}

function extractSearchCandidates(result: OperationExecutionResult): WorkflowContext[] {
  const output = result.output;
  if (typeof output !== "object" || output === null || Array.isArray(output)) {
    return [];
  }

  const rawResults = (output as Record<string, unknown>).results;
  if (!Array.isArray(rawResults)) {
    return [];
  }

  return rawResults.filter((candidate) => typeof candidate === "object" && candidate !== null) as WorkflowContext[];
}

async function runWithConcurrencyLimit<TInput, TOutput>(
  items: TInput[],
  concurrency: number,
  worker: (item: TInput, index: number) => Promise<TOutput>,
): Promise<TOutput[]> {
  const results = new Array<TOutput>(items.length);
  let nextIndex = 0;

  const runners = Array.from({ length: Math.min(concurrency, items.length) }, async () => {
    while (nextIndex < items.length) {
      const currentIndex = nextIndex;
      nextIndex += 1;
      results[currentIndex] = await worker(items[currentIndex] as TInput, currentIndex);
    }
  });

  await Promise.all(runners);
  return results;
}

async function emitCompanyStepTimelineEvent(
  client: InternalApiClient,
  payload: PersonSearchEnrichmentWorkflowPayload,
  stepResultId: string,
  stepPosition: number,
  operationId: PersonWorkflowOperationId,
  stepStatus: "succeeded" | "failed" | "skipped",
  cumulativeContext: WorkflowContext,
  options: {
    operationResult?: Record<string, unknown> | null;
    skipReason?: string | null;
    errorMessage?: string | null;
    errorDetails?: Record<string, unknown> | null;
  } = {},
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
      stepPosition,
      operationId,
      stepStatus,
      skipReason: options.skipReason ?? null,
      errorMessage: options.errorMessage ?? null,
      errorDetails: options.errorDetails ?? null,
      operationResult: options.operationResult ?? null,
    });
  } catch (error) {
    logger.warn("person-search-enrichment timeline event failed", {
      pipeline_run_id: payload.pipeline_run_id,
      step_result_id: stepResultId,
      step_position: stepPosition,
      operation_id: operationId,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

async function failWorkflow(params: {
  client: InternalApiClient;
  payload: PersonSearchEnrichmentWorkflowPayload;
  cumulativeContext: WorkflowContext;
  executedSteps: PersonSearchEnrichmentWorkflowResult["executed_steps"];
  message: string;
  failedStep: PersonWorkflowDefinitionStep;
  failedStepReference?: WorkflowStepReference;
  failedOperationResult?: OperationExecutionResult;
  errorDetails?: Record<string, unknown>;
  peopleDiscovered: number;
  personOutcomes: PersonBatchOutcome[];
}): Promise<PersonSearchEnrichmentWorkflowResult> {
  if (params.failedStepReference) {
    await markStepResultFailed(params.client, {
      stepResultId: params.failedStepReference.step_result_id,
      inputPayload: params.cumulativeContext,
      operationResult: params.failedOperationResult,
      cumulativeContext: params.cumulativeContext,
      errorMessage: params.message,
      errorDetails:
        params.errorDetails ??
        (params.failedOperationResult
          ? {
              operation_id: params.failedStep.operationId,
              missing_inputs: params.failedOperationResult.missing_inputs ?? [],
            }
          : { operation_id: params.failedStep.operationId }),
    });

    await emitCompanyStepTimelineEvent(
      params.client,
      params.payload,
      params.failedStepReference.step_result_id,
      params.failedStep.position,
      params.failedStep.operationId,
      "failed",
      params.cumulativeContext,
      {
        operationResult: (params.failedOperationResult as unknown as Record<string, unknown>) ?? null,
        errorMessage: params.message,
        errorDetails: params.errorDetails,
      },
    );
  }

  for (const remainingStep of params.payload.step_results.filter(
    (candidate) => candidate.step_position > params.failedStep.position,
  )) {
    await markStepResultSkipped(params.client, {
      stepResultId: remainingStep.step_result_id,
      inputPayload: params.cumulativeContext,
      skipReason: "upstream_step_failed",
      metadata: {
        failed_step_position: params.failedStep.position,
        failed_operation_id: params.failedStep.operationId,
      },
    });

    const stepDefinition = PERSON_SEARCH_ENRICHMENT_STEPS.find(
      (candidate) => candidate.position === remainingStep.step_position,
    );
    if (stepDefinition) {
      await emitCompanyStepTimelineEvent(
        params.client,
        params.payload,
        remainingStep.step_result_id,
        stepDefinition.position,
        stepDefinition.operationId,
        "skipped",
        params.cumulativeContext,
        {
          skipReason: "upstream_step_failed",
          errorMessage: "Skipped because an upstream step failed",
          errorDetails: {
            failed_step_position: params.failedStep.position,
            failed_operation_id: params.failedStep.operationId,
          },
        },
      );
    }
  }

  await markPipelineRunFailed(params.client, {
    pipelineRunId: params.payload.pipeline_run_id,
    errorMessage: params.message,
    errorDetails: params.errorDetails ?? null,
  });

  return {
    pipeline_run_id: params.payload.pipeline_run_id,
    status: "failed",
    cumulative_context: params.cumulativeContext,
    failed_step_position: params.failedStep.position,
    error: params.message,
    people_discovered: params.peopleDiscovered,
    people_persisted: params.personOutcomes.filter((outcome) => outcome.persisted).length,
    person_results: params.personOutcomes.map(buildPersonOutcomeSummary),
    executed_steps: params.executedSteps,
  };
}

export async function runPersonSearchEnrichmentWorkflow(
  payload: PersonSearchEnrichmentWorkflowPayload,
  dependencies: PersonSearchEnrichmentWorkflowDependencies = {},
): Promise<PersonSearchEnrichmentWorkflowResult> {
  const client = getClient(payload, dependencies);
  const executedSteps: PersonSearchEnrichmentWorkflowResult["executed_steps"] = [];
  let cumulativeContext = buildPersonSearchSeedContext(
    payload.company_domain,
    payload.initial_context ?? {},
  );

  await markPipelineRunRunning(client, payload.pipeline_run_id);
  validateWorkflowStepReferences(payload.step_results);

  const stepReferenceMap = getStepReferenceMap(payload.step_results);
  const maxPeople = toBoundedInteger(payload.max_people, { fallback: 25, min: 1, max: 100 });
  const concurrency = toBoundedInteger(payload.per_person_concurrency, {
    fallback: 4,
    min: 1,
    max: 12,
  });

  logger.info("person-search-enrichment workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    company_domain: payload.company_domain,
    max_people: maxPeople,
    per_person_concurrency: concurrency,
  });

  const searchStep = PERSON_SEARCH_ENRICHMENT_STEPS[0];
  const searchStepReference = stepReferenceMap.get(searchStep.position);

  if (!searchStepReference) {
    return failWorkflow({
      client,
      payload,
      cumulativeContext,
      executedSteps,
      message: `Missing step_result mapping for position ${searchStep.position}`,
      failedStep: searchStep,
      errorDetails: { step_position: searchStep.position, operation_id: searchStep.operationId },
      peopleDiscovered: 0,
      personOutcomes: [],
    });
  }

  await markStepResultRunning(client, {
    stepResultId: searchStepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  let searchResult: OperationExecutionResult;

  try {
    searchResult = await executeOperation(client, {
      operationId: searchStep.operationId,
      entityType: "person",
      input: cumulativeContext,
      options: { max_results: maxPeople },
    });
  } catch (error) {
    const message =
      error instanceof Error
        ? `Operation transport failed: ${searchStep.operationId}: ${error.message}`
        : `Operation transport failed: ${searchStep.operationId}: ${String(error)}`;

    return failWorkflow({
      client,
      payload,
      cumulativeContext,
      executedSteps,
      message,
      failedStep: searchStep,
      failedStepReference: searchStepReference,
      errorDetails: { operation_id: searchStep.operationId },
      peopleDiscovered: 0,
      personOutcomes: [],
    });
  }

  cumulativeContext = mergeStepOutput(cumulativeContext, searchResult.output);

  if (isFailedOperationResult(searchResult)) {
    return failWorkflow({
      client,
      payload,
      cumulativeContext,
      executedSteps,
      message: `Operation failed: ${searchStep.operationId}`,
      failedStep: searchStep,
      failedStepReference: searchStepReference,
      failedOperationResult: searchResult,
      errorDetails: {
        operation_id: searchStep.operationId,
        missing_inputs: searchResult.missing_inputs ?? [],
      },
      peopleDiscovered: 0,
      personOutcomes: [],
    });
  }

  const candidates = extractSearchCandidates(searchResult).slice(0, maxPeople);
  cumulativeContext = mergeStepOutput(cumulativeContext, {
    people_discovered_count: candidates.length,
  });

  await markStepResultSucceeded(client, {
    stepResultId: searchStepReference.step_result_id,
    operationResult: searchResult,
    cumulativeContext,
  });
  await emitCompanyStepTimelineEvent(
    client,
    payload,
    searchStepReference.step_result_id,
    searchStep.position,
    searchStep.operationId,
    "succeeded",
    cumulativeContext,
    { operationResult: searchResult as unknown as Record<string, unknown> },
  );

  executedSteps.push({
    step_position: searchStep.position,
    operation_id: searchStep.operationId,
    status: "succeeded",
    operation_status: searchResult.status,
  });

  if (candidates.length === 0) {
    for (const step of PERSON_SEARCH_ENRICHMENT_STEPS.slice(1)) {
      const stepReference = stepReferenceMap.get(step.position);
      if (!stepReference) {
        continue;
      }
      await markStepResultSkipped(client, {
        stepResultId: stepReference.step_result_id,
        inputPayload: cumulativeContext,
        skipReason: "no_people_discovered",
        metadata: {
          operation_id: step.operationId,
          step_position: step.position,
        },
      });
      await emitCompanyStepTimelineEvent(
        client,
        payload,
        stepReference.step_result_id,
        step.position,
        step.operationId,
        "skipped",
        cumulativeContext,
        { skipReason: "no_people_discovered" },
      );
      executedSteps.push({
        step_position: step.position,
        operation_id: step.operationId,
        status: "skipped",
      });
    }

    await markPipelineRunSucceeded(client, payload.pipeline_run_id);
    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "succeeded",
      cumulative_context: cumulativeContext,
      people_discovered: 0,
      people_persisted: 0,
      person_results: [],
      executed_steps: executedSteps,
    };
  }

  const profileStep = PERSON_SEARCH_ENRICHMENT_STEPS[1];
  const profileStepReference = stepReferenceMap.get(profileStep.position);

  if (!profileStepReference) {
    return failWorkflow({
      client,
      payload,
      cumulativeContext,
      executedSteps,
      message: `Missing step_result mapping for position ${profileStep.position}`,
      failedStep: profileStep,
      errorDetails: { step_position: profileStep.position, operation_id: profileStep.operationId },
      peopleDiscovered: candidates.length,
      personOutcomes: [],
    });
  }

  await markStepResultRunning(client, {
    stepResultId: profileStepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  const profiledPeople = await runWithConcurrencyLimit(candidates, concurrency, async (candidate, index) => {
    const seededContext = buildPersonCandidateContext(cumulativeContext, candidate);
    const outcome: PersonBatchOutcome = {
      person_index: index,
      persisted: false,
      last_operation_id: "person.search",
      profile_status: "not_found",
      contact_status: "not_attempted",
      errors: [],
      context: seededContext,
    };

    try {
      const profileResult = await executeOperation(client, {
        operationId: profileStep.operationId,
        entityType: "person",
        input: seededContext,
        options: { include_work_history: payload.include_work_history === true },
      });

      if (profileResult.status === "found" || profileResult.status === "not_found") {
        outcome.context = buildPersistablePersonContext(
          mergeStepOutput(seededContext, profileResult.output),
        );
        outcome.profile_status = profileResult.status === "found" ? "found" : "not_found";
        outcome.last_operation_id = profileStep.operationId;
        return outcome;
      }

      outcome.profile_status = "failed";
      outcome.errors.push(`profile:${profileResult.status}`);
      return outcome;
    } catch (error) {
      outcome.profile_status = "failed";
      outcome.errors.push(
        error instanceof Error ? `profile_transport:${error.message}` : `profile_transport:${String(error)}`,
      );
      return outcome;
    }
  });

  const profileSummary: BatchSummary = profiledPeople.reduce(
    (summary, outcome) => {
      summary.processed_count += 1;
      if (outcome.profile_status === "found") {
        summary.succeeded_count += 1;
      } else if (outcome.profile_status === "not_found") {
        summary.not_found_count += 1;
      } else {
        summary.failed_count += 1;
      }
      return summary;
    },
    {
      processed_count: 0,
      succeeded_count: 0,
      failed_count: 0,
      not_found_count: 0,
    },
  );

  const profileBatchResult = buildBatchOperationResult({
    pipelineRunId: payload.pipeline_run_id,
    operationId: profileStep.operationId,
    status: profileSummary.succeeded_count > 0 ? "found" : "not_found",
    output: {
      ...profileSummary,
      people: buildPeopleListSummary(profiledPeople),
    },
  });

  cumulativeContext = mergeStepOutput(cumulativeContext, {
    people_profiled_count: profileSummary.succeeded_count,
    people_profile_failures_count: profileSummary.failed_count,
  });

  await markStepResultSucceeded(client, {
    stepResultId: profileStepReference.step_result_id,
    operationResult: profileBatchResult,
    cumulativeContext,
  });
  await emitCompanyStepTimelineEvent(
    client,
    payload,
    profileStepReference.step_result_id,
    profileStep.position,
    profileStep.operationId,
    "succeeded",
    cumulativeContext,
    { operationResult: profileBatchResult as unknown as Record<string, unknown> },
  );

  executedSteps.push({
    step_position: profileStep.position,
    operation_id: profileStep.operationId,
    status: "succeeded",
    operation_status: profileBatchResult.status,
  });

  const emailStep = PERSON_SEARCH_ENRICHMENT_STEPS[2];
  const emailStepReference = stepReferenceMap.get(emailStep.position);

  if (!emailStepReference) {
    return failWorkflow({
      client,
      payload,
      cumulativeContext,
      executedSteps,
      message: `Missing step_result mapping for position ${emailStep.position}`,
      failedStep: emailStep,
      errorDetails: { step_position: emailStep.position, operation_id: emailStep.operationId },
      peopleDiscovered: candidates.length,
      personOutcomes: profiledPeople,
    });
  }

  await markStepResultRunning(client, {
    stepResultId: emailStepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  const finalizedPeople = await runWithConcurrencyLimit(profiledPeople, concurrency, async (profiled) => {
    const outcome: PersonBatchOutcome = {
      ...profiled,
      context: buildPersistablePersonContext(profiled.context),
      errors: [...profiled.errors],
      contact_status: "not_attempted",
    };

    if (outcome.context.full_name === undefined && outcome.context.linkedin_url === undefined) {
      outcome.errors.push("person_identity_missing");
    }

    try {
      const emailResult = await executeOperation(client, {
        operationId: emailStep.operationId,
        entityType: "person",
        input: outcome.context,
      });

      if (emailResult.status === "found" || emailResult.status === "not_found") {
        outcome.context = buildPersistablePersonContext(
          mergeStepOutput(outcome.context, emailResult.output),
        );
        outcome.contact_status = emailResult.status === "found" ? "found" : "not_found";
        outcome.last_operation_id = emailStep.operationId;
      } else {
        outcome.contact_status = "failed";
        outcome.errors.push(`contact:${emailResult.status}`);
      }
    } catch (error) {
      outcome.contact_status = "failed";
      outcome.errors.push(
        error instanceof Error ? `contact_transport:${error.message}` : `contact_transport:${String(error)}`,
      );
    }

    try {
      const persisted = await upsertEntityStateConfirmed(client, {
        pipelineRunId: payload.pipeline_run_id,
        entityType: "person",
        cumulativeContext: outcome.context,
        lastOperationId: outcome.last_operation_id,
      });
      outcome.entity_id = persisted.entity_id;
      outcome.persisted = true;
    } catch (error) {
      outcome.persisted = false;
      outcome.errors.push(
        error instanceof Error ? `persistence:${error.message}` : `persistence:${String(error)}`,
      );
    }

    return outcome;
  });

  const finalSummary: BatchSummary = finalizedPeople.reduce(
    (summary, outcome) => {
      summary.processed_count += 1;
      if (outcome.contact_status === "found") {
        summary.succeeded_count += 1;
      } else if (outcome.contact_status === "not_found" || outcome.contact_status === "not_attempted") {
        summary.not_found_count += 1;
      } else {
        summary.failed_count += 1;
      }

      if (outcome.persisted) {
        summary.persisted_count = (summary.persisted_count ?? 0) + 1;
      } else {
        summary.persistence_failed_count = (summary.persistence_failed_count ?? 0) + 1;
      }
      return summary;
    },
    {
      processed_count: 0,
      succeeded_count: 0,
      failed_count: 0,
      not_found_count: 0,
      persisted_count: 0,
      persistence_failed_count: 0,
    },
  );

  cumulativeContext = mergeStepOutput(cumulativeContext, {
    people_contactable_count: finalSummary.succeeded_count,
    people_persisted_count: finalSummary.persisted_count ?? 0,
  });

  const finalBatchResult = buildBatchOperationResult({
    pipelineRunId: payload.pipeline_run_id,
    operationId: emailStep.operationId,
    status:
      (finalSummary.persisted_count ?? 0) > 0 || finalSummary.succeeded_count > 0 ? "found" : "not_found",
    output: {
      ...finalSummary,
      people: buildPeopleListSummary(finalizedPeople),
    },
  });

  const persistenceFailures = finalSummary.persistence_failed_count ?? 0;
  const persistedPeople = finalSummary.persisted_count ?? 0;

  if (persistenceFailures > 0 || persistedPeople === 0) {
    return failWorkflow({
      client,
      payload,
      cumulativeContext,
      executedSteps,
      message:
        persistenceFailures > 0
          ? `Entity state upsert failed for ${persistenceFailures} people`
          : "No people were persisted",
      failedStep: emailStep,
      failedStepReference: emailStepReference,
      failedOperationResult: finalBatchResult,
      errorDetails: {
        operation_id: emailStep.operationId,
        persisted_count: persistedPeople,
        persistence_failed_count: persistenceFailures,
      },
      peopleDiscovered: candidates.length,
      personOutcomes: finalizedPeople,
    });
  }

  await markStepResultSucceeded(client, {
    stepResultId: emailStepReference.step_result_id,
    operationResult: finalBatchResult,
    cumulativeContext,
  });
  await emitCompanyStepTimelineEvent(
    client,
    payload,
    emailStepReference.step_result_id,
    emailStep.position,
    emailStep.operationId,
    "succeeded",
    cumulativeContext,
    { operationResult: finalBatchResult as unknown as Record<string, unknown> },
  );

  executedSteps.push({
    step_position: emailStep.position,
    operation_id: emailStep.operationId,
    status: "succeeded",
    operation_status: finalBatchResult.status,
  });

  await markPipelineRunSucceeded(client, payload.pipeline_run_id);

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    people_discovered: candidates.length,
    people_persisted: persistedPeople,
    person_results: finalizedPeople.map(buildPersonOutcomeSummary),
    executed_steps: executedSteps,
  };
}

export const __testables = {
  PERSON_SEARCH_ENRICHMENT_STEPS,
  validateWorkflowStepReferences,
};
