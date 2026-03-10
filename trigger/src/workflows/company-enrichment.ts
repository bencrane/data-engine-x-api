import { logger } from "@trigger.dev/sdk/v3";

import {
  buildCompanySeedContext,
  hasLinkedinUrl,
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
  skipRemainingWorkflowSteps,
  WorkflowStepReference,
} from "./lineage.js";
import {
  executeOperation,
  isFailedOperationResult,
  OperationExecutionResult,
} from "./operations.js";
import { upsertEntityStateConfirmed } from "./persistence.js";

type CompanyWorkflowOperationId =
  | "company.enrich.profile"
  | "company.research.infer_linkedin_url";

interface CompanyWorkflowDefinitionStep {
  position: number;
  operationId: CompanyWorkflowOperationId;
  shouldSkip?: (context: WorkflowContext) => boolean;
  skipReason?: string;
}

export interface CompanyEnrichmentWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  company_domain: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;
  api_url?: string;
  internal_api_key?: string;
}

export interface CompanyEnrichmentWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  entity_id?: string;
  last_operation_id?: string | null;
  failed_step_position?: number;
  error?: string;
  executed_steps: Array<{
    step_position: number;
    operation_id: CompanyWorkflowOperationId;
    status: "succeeded" | "skipped";
    operation_status?: string;
  }>;
}

export interface CompanyEnrichmentWorkflowDependencies {
  client?: InternalApiClient;
}

const COMPANY_ENRICHMENT_STEPS: CompanyWorkflowDefinitionStep[] = [
  {
    position: 1,
    operationId: "company.enrich.profile",
  },
  {
    position: 2,
    operationId: "company.research.infer_linkedin_url",
    shouldSkip: hasLinkedinUrl,
    skipReason: "linkedin_url_already_present",
  },
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
  const expectedPositions = COMPANY_ENRICHMENT_STEPS.map((step) => step.position).sort((a, b) => a - b);
  const actualPositions = stepResults.map((step) => step.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `Company enrichment workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  for (let index = 0; index < expectedPositions.length; index += 1) {
    if (expectedPositions[index] !== actualPositions[index]) {
      throw new Error(
        `Company enrichment workflow step_results must match positions ${expectedPositions.join(", ")}`,
      );
    }
  }
}

async function failWorkflow(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  cumulativeContext: WorkflowContext;
  executedSteps: CompanyEnrichmentWorkflowResult["executed_steps"];
  message: string;
  failedStep?: CompanyWorkflowDefinitionStep;
  failedStepReference?: WorkflowStepReference;
  failedOperationResult?: OperationExecutionResult;
  errorDetails?: Record<string, unknown>;
  remainingSteps?: WorkflowStepReference[];
}): Promise<CompanyEnrichmentWorkflowResult> {
  if (params.failedStepReference && params.failedStep) {
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
  }

  if (params.remainingSteps && params.failedStep) {
    await skipRemainingWorkflowSteps(params.client, {
      remainingSteps: params.remainingSteps,
      cumulativeContext: params.cumulativeContext,
      failedStepPosition: params.failedStep.position,
      failedOperationId: params.failedStep.operationId,
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
    failed_step_position: params.failedStep?.position,
    error: params.message,
    executed_steps: params.executedSteps,
  };
}

function getClient(
  payload: CompanyEnrichmentWorkflowPayload,
  dependencies: CompanyEnrichmentWorkflowDependencies,
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

export async function runCompanyEnrichmentWorkflow(
  payload: CompanyEnrichmentWorkflowPayload,
  dependencies: CompanyEnrichmentWorkflowDependencies = {},
): Promise<CompanyEnrichmentWorkflowResult> {
  const client = getClient(payload, dependencies);
  const executedSteps: CompanyEnrichmentWorkflowResult["executed_steps"] = [];
  let cumulativeContext = buildCompanySeedContext(payload.company_domain, payload.initial_context ?? {});
  let lastSuccessfulOperationId: string | null = null;

  await markPipelineRunRunning(client, payload.pipeline_run_id);
  validateWorkflowStepReferences(payload.step_results);

  const stepReferenceMap = getStepReferenceMap(payload.step_results);

  logger.info("company-enrichment workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    company_domain: payload.company_domain,
    step_count: COMPANY_ENRICHMENT_STEPS.length,
  });

  for (let index = 0; index < COMPANY_ENRICHMENT_STEPS.length; index += 1) {
    const step = COMPANY_ENRICHMENT_STEPS[index];
    const stepReference = stepReferenceMap.get(step.position);

    if (!stepReference) {
      return failWorkflow({
        client,
        pipelineRunId: payload.pipeline_run_id,
        cumulativeContext,
        executedSteps,
        message: `Missing step_result mapping for position ${step.position}`,
        failedStep: step,
        errorDetails: { step_position: step.position, operation_id: step.operationId },
      });
    }

    if (step.shouldSkip?.(cumulativeContext)) {
      await markStepResultSkipped(client, {
        stepResultId: stepReference.step_result_id,
        inputPayload: cumulativeContext,
        skipReason: step.skipReason ?? "workflow_condition_not_met",
        metadata: {
          operation_id: step.operationId,
          step_position: step.position,
        },
      });

      executedSteps.push({
        step_position: step.position,
        operation_id: step.operationId,
        status: "skipped",
      });

      continue;
    }

    await markStepResultRunning(client, {
      stepResultId: stepReference.step_result_id,
      inputPayload: cumulativeContext,
    });

    let operationResult: OperationExecutionResult;

    try {
      operationResult = await executeOperation(client, {
        operationId: step.operationId,
        entityType: "company",
        input: cumulativeContext,
      });
    } catch (error) {
      const message =
        error instanceof Error
          ? `Operation transport failed: ${step.operationId}: ${error.message}`
          : `Operation transport failed: ${step.operationId}: ${String(error)}`;

      return failWorkflow({
        client,
        pipelineRunId: payload.pipeline_run_id,
        cumulativeContext,
        executedSteps,
        message,
        failedStep: step,
        failedStepReference: stepReference,
        errorDetails: { operation_id: step.operationId },
        remainingSteps: payload.step_results.filter((candidate) => candidate.step_position > step.position),
      });
    }

    cumulativeContext = mergeStepOutput(cumulativeContext, operationResult.output);

    if (isFailedOperationResult(operationResult)) {
      return failWorkflow({
        client,
        pipelineRunId: payload.pipeline_run_id,
        cumulativeContext,
        executedSteps,
        message: `Operation failed: ${step.operationId}`,
        failedStep: step,
        failedStepReference: stepReference,
        failedOperationResult: operationResult,
        errorDetails: {
          operation_id: step.operationId,
          missing_inputs: operationResult.missing_inputs ?? [],
        },
        remainingSteps: payload.step_results.filter((candidate) => candidate.step_position > step.position),
      });
    }

    await markStepResultSucceeded(client, {
      stepResultId: stepReference.step_result_id,
      operationResult,
      cumulativeContext,
    });

    lastSuccessfulOperationId = step.operationId;
    executedSteps.push({
      step_position: step.position,
      operation_id: step.operationId,
      status: "succeeded",
      operation_status: operationResult.status,
    });
  }

  await markPipelineRunSucceeded(client, payload.pipeline_run_id);

  try {
    const upsertedEntity = await upsertEntityStateConfirmed(client, {
      pipelineRunId: payload.pipeline_run_id,
      entityType: "company",
      cumulativeContext,
      lastOperationId: lastSuccessfulOperationId,
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "succeeded",
      cumulative_context: cumulativeContext,
      entity_id: upsertedEntity.entity_id,
      last_operation_id: lastSuccessfulOperationId,
      executed_steps: executedSteps,
    };
  } catch (error) {
    const message =
      error instanceof Error
        ? `Entity state upsert failed: ${error.message}`
        : `Entity state upsert failed: ${String(error)}`;

    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: { last_operation_id: lastSuccessfulOperationId },
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      last_operation_id: lastSuccessfulOperationId,
      error: message,
      executed_steps: executedSteps,
    };
  }
}

export const __testables = {
  COMPANY_ENRICHMENT_STEPS,
  validateWorkflowStepReferences,
};
