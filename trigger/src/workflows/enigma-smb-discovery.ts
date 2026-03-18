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
  markStepResultSkipped,
  WorkflowStepReference,
} from "./lineage.js";
import { OperationExecutionResult } from "./operations.js";
import {
  EntityStateUpsertResult,
  upsertEntityStateConfirmed,
  writeDedicatedTableConfirmed,
} from "./persistence.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface EnigmaSmBDiscoveryWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  submission_id?: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;

  // Discovery parameters
  prompt: string;
  geography_state?: string;
  geography_city?: string;
  brand_limit?: number;

  // Enrichment flags (control credit spend)
  enrich_card_revenue?: boolean;
  enrich_locations?: boolean;
  location_limit?: number;
  include_location_card_transactions?: boolean;
  include_location_ranks?: boolean;
  include_location_reviews?: boolean;
  include_location_roles?: boolean;

  // Override defaults
  api_url?: string;
  internal_api_key?: string;
}

export interface EnigmaSmBDiscoveryWorkflowResult {
  pipeline_run_id: string;
  status: "succeeded" | "failed";
  cumulative_context: WorkflowContext;
  entity_id?: string;
  last_operation_id?: string | null;
  error?: string;
  executed_steps: Array<{
    step_position: number;
    operation_id: string;
    status: "succeeded" | "failed" | "skipped";
    operation_status?: string;
  }>;
  persistence: {
    entity_state_confirmed: boolean;
    brand_discoveries_confirmed: boolean;
    location_enrichments_confirmed: boolean;
  };
}

interface EnigmaSmBWorkflowDefinitionStep {
  position: number;
  operationId: string;
  conditional: boolean;
}

interface BrandDiscoveryDedicatedWriteResult {
  id?: string;
  [key: string]: unknown;
}

interface LocationEnrichmentDedicatedWriteResult {
  id?: string;
  [key: string]: unknown;
}

interface PersistenceOutcome {
  entityStateConfirmed: boolean;
  entityId?: string;
  brandDiscoveriesConfirmed: boolean;
  locationEnrichmentsConfirmed: boolean;
  errors: string[];
  errorDetails: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const BRAND_DISCOVERY_OPERATION_ID = "company.search.enigma.brands";
const CARD_REVENUE_OPERATION_ID = "company.enrich.card_revenue";
const LOCATIONS_OPERATION_ID = "company.enrich.locations";

const ENIGMA_SMB_DISCOVERY_STEPS: EnigmaSmBWorkflowDefinitionStep[] = [
  { position: 1, operationId: BRAND_DISCOVERY_OPERATION_ID, conditional: false },
  { position: 2, operationId: CARD_REVENUE_OPERATION_ID, conditional: true },
  { position: 3, operationId: LOCATIONS_OPERATION_ID, conditional: true },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getOptionalString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  return normalized.length > 0 ? normalized : undefined;
}

function getStepReferenceMap(
  stepResults: WorkflowStepReference[],
): Map<number, WorkflowStepReference> {
  const map = new Map<number, WorkflowStepReference>();
  for (const sr of stepResults) {
    if (map.has(sr.step_position)) {
      throw new Error(`Duplicate step_result mapping for position ${sr.step_position}`);
    }
    map.set(sr.step_position, sr);
  }
  return map;
}

function validateWorkflowStepReferences(stepResults: WorkflowStepReference[]): void {
  const expectedPositions = ENIGMA_SMB_DISCOVERY_STEPS.map((s) => s.position).sort((a, b) => a - b);
  const actualPositions = stepResults.map((s) => s.step_position).sort((a, b) => a - b);

  if (expectedPositions.length !== actualPositions.length) {
    throw new Error(
      `Enigma SMB discovery workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  for (let i = 0; i < expectedPositions.length; i += 1) {
    if (expectedPositions[i] !== actualPositions[i]) {
      throw new Error(
        `Enigma SMB discovery workflow step_results must match positions ${expectedPositions.join(", ")}`,
      );
    }
  }
}

function getClient(
  payload: EnigmaSmBDiscoveryWorkflowPayload,
): InternalApiClient {
  return createInternalApiClient({
    authContext: {
      orgId: payload.org_id,
      companyId: payload.company_id,
    },
    apiUrl: payload.api_url,
    internalApiKey: payload.internal_api_key,
  });
}

// ---------------------------------------------------------------------------
// Execute operation via internal API
// ---------------------------------------------------------------------------

async function executeOperation(
  client: InternalApiClient,
  operationId: string,
  entityType: string,
  inputData: Record<string, unknown>,
): Promise<OperationExecutionResult> {
  return client.post<OperationExecutionResult>("/api/v1/execute", {
    operation_id: operationId,
    entity_type: entityType,
    input: inputData,
  });
}

// ---------------------------------------------------------------------------
// Confirmed write wrappers
// ---------------------------------------------------------------------------

async function writeEnigmaBrandDiscoveriesConfirmed(
  client: InternalApiClient,
  params: {
    discoveryPrompt: string;
    brands: Array<Record<string, unknown>>;
    companyId?: string;
    geographyState?: string;
    geographyCity?: string;
    discoveredByOperationId?: string;
    submissionId?: string;
    pipelineRunId: string;
  },
): Promise<BrandDiscoveryDedicatedWriteResult[]> {
  return writeDedicatedTableConfirmed<BrandDiscoveryDedicatedWriteResult[]>(client, {
    path: "/api/internal/enigma-brand-discoveries/upsert",
    payload: {
      discovery_prompt: params.discoveryPrompt,
      brands: params.brands,
      company_id: params.companyId,
      geography_state: params.geographyState,
      geography_city: params.geographyCity,
      discovered_by_operation_id: params.discoveredByOperationId ?? BRAND_DISCOVERY_OPERATION_ID,
      source_submission_id: params.submissionId,
      source_pipeline_run_id: params.pipelineRunId,
    },
    validate: (response) => Array.isArray(response) && response.length > 0,
    confirmationErrorMessage: "Enigma brand discoveries dedicated-table write could not be confirmed",
  });
}

async function writeEnigmaLocationEnrichmentsConfirmed(
  client: InternalApiClient,
  params: {
    enigmaBrandId: string;
    brandName?: string;
    locations: Array<Record<string, unknown>>;
    companyId?: string;
    enrichedByOperationId?: string;
    submissionId?: string;
    pipelineRunId: string;
  },
): Promise<LocationEnrichmentDedicatedWriteResult[]> {
  return writeDedicatedTableConfirmed<LocationEnrichmentDedicatedWriteResult[]>(client, {
    path: "/api/internal/enigma-location-enrichments/upsert",
    payload: {
      enigma_brand_id: params.enigmaBrandId,
      brand_name: params.brandName,
      locations: params.locations,
      company_id: params.companyId,
      enriched_by_operation_id: params.enrichedByOperationId ?? LOCATIONS_OPERATION_ID,
      source_submission_id: params.submissionId,
      source_pipeline_run_id: params.pipelineRunId,
    },
    validate: (response) => Array.isArray(response) && response.length > 0,
    confirmationErrorMessage: "Enigma location enrichments dedicated-table write could not be confirmed",
  });
}

// ---------------------------------------------------------------------------
// Failure helper
// ---------------------------------------------------------------------------

async function failWorkflow(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  stepReference?: WorkflowStepReference;
  cumulativeContext: WorkflowContext;
  executedSteps: EnigmaSmBDiscoveryWorkflowResult["executed_steps"];
  message: string;
  failedOperationResult?: OperationExecutionResult;
  errorDetails?: Record<string, unknown> | null;
  persistence?: EnigmaSmBDiscoveryWorkflowResult["persistence"];
}): Promise<EnigmaSmBDiscoveryWorkflowResult> {
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
      params.executedSteps.length > 0
        ? params.executedSteps[params.executedSteps.length - 1]?.operation_id
        : null,
    error: params.message,
    executed_steps: params.executedSteps,
    persistence: params.persistence ?? {
      entity_state_confirmed: false,
      brand_discoveries_confirmed: false,
      location_enrichments_confirmed: false,
    },
  };
}

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

async function persistResults(params: {
  client: InternalApiClient;
  payload: EnigmaSmBDiscoveryWorkflowPayload;
  cumulativeContext: WorkflowContext;
  brands: Array<Record<string, unknown>>;
  hasLocations: boolean;
}): Promise<PersistenceOutcome> {
  const outcome: PersistenceOutcome = {
    entityStateConfirmed: false,
    brandDiscoveriesConfirmed: false,
    locationEnrichmentsConfirmed: false,
    errors: [],
    errorDetails: {},
  };

  // 1. Entity state upsert
  try {
    const entityState = await upsertEntityStateConfirmed(params.client, {
      pipelineRunId: params.payload.pipeline_run_id,
      entityType: "company",
      cumulativeContext: params.cumulativeContext,
      lastOperationId: params.hasLocations ? LOCATIONS_OPERATION_ID : BRAND_DISCOVERY_OPERATION_ID,
    });
    outcome.entityStateConfirmed = true;
    outcome.entityId = entityState.entity_id;
  } catch (error) {
    outcome.errors.push(
      error instanceof Error
        ? `Entity state upsert failed: ${error.message}`
        : `Entity state upsert failed: ${String(error)}`,
    );
    outcome.errorDetails.entity_state = {
      confirmed: false,
      error: error instanceof Error ? error.message : String(error),
    };
  }

  // 2. Brand discoveries dedicated table
  if (params.brands.length > 0) {
    try {
      await writeEnigmaBrandDiscoveriesConfirmed(params.client, {
        discoveryPrompt: params.payload.prompt,
        brands: params.brands,
        companyId: params.payload.company_id,
        geographyState: params.payload.geography_state,
        geographyCity: params.payload.geography_city,
        submissionId: params.payload.submission_id,
        pipelineRunId: params.payload.pipeline_run_id,
      });
      outcome.brandDiscoveriesConfirmed = true;
    } catch (error) {
      outcome.errors.push(
        error instanceof Error
          ? `Brand discoveries upsert failed: ${error.message}`
          : `Brand discoveries upsert failed: ${String(error)}`,
      );
      outcome.errorDetails.brand_discoveries = {
        confirmed: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  } else {
    outcome.brandDiscoveriesConfirmed = true;
  }

  // 3. Location enrichments per brand
  if (params.hasLocations) {
    let allLocationsConfirmed = true;
    for (const brand of params.brands) {
      const brandLocations = brand.locations;
      if (!Array.isArray(brandLocations) || brandLocations.length === 0) continue;

      const enigmaBrandId = typeof brand.enigma_brand_id === "string" ? brand.enigma_brand_id : undefined;
      if (!enigmaBrandId) continue;

      try {
        await writeEnigmaLocationEnrichmentsConfirmed(params.client, {
          enigmaBrandId,
          brandName: typeof brand.brand_name === "string" ? brand.brand_name : undefined,
          locations: brandLocations as Array<Record<string, unknown>>,
          companyId: params.payload.company_id,
          submissionId: params.payload.submission_id,
          pipelineRunId: params.payload.pipeline_run_id,
        });
      } catch (error) {
        allLocationsConfirmed = false;
        outcome.errors.push(
          error instanceof Error
            ? `Location enrichments upsert failed for brand ${enigmaBrandId}: ${error.message}`
            : `Location enrichments upsert failed for brand ${enigmaBrandId}: ${String(error)}`,
        );
        outcome.errorDetails[`location_enrichments_${enigmaBrandId}`] = {
          confirmed: false,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
    outcome.locationEnrichmentsConfirmed = allLocationsConfirmed;
  } else {
    outcome.locationEnrichmentsConfirmed = true;
  }

  // Update entity details in outcome
  if (outcome.entityStateConfirmed) {
    outcome.errorDetails.entity_state = { confirmed: true, entity_id: outcome.entityId };
  }
  if (outcome.brandDiscoveriesConfirmed) {
    outcome.errorDetails.brand_discoveries = { confirmed: true };
  }
  if (outcome.locationEnrichmentsConfirmed) {
    outcome.errorDetails.location_enrichments = { confirmed: true };
  }

  return outcome;
}

// ---------------------------------------------------------------------------
// Main workflow
// ---------------------------------------------------------------------------

export async function runEnigmaSmBDiscoveryWorkflow(
  payload: EnigmaSmBDiscoveryWorkflowPayload,
): Promise<EnigmaSmBDiscoveryWorkflowResult> {
  const client = getClient(payload);
  const executedSteps: EnigmaSmBDiscoveryWorkflowResult["executed_steps"] = [];
  let cumulativeContext: WorkflowContext = payload.initial_context ? { ...payload.initial_context } : {};

  // Validate inputs
  const normalizedPrompt = getOptionalString(payload.prompt);
  if (!normalizedPrompt) {
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: "Invalid Enigma SMB discovery workflow input: prompt is required",
    });
    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      error: "Invalid Enigma SMB discovery workflow input: prompt is required",
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: false,
        brand_discoveries_confirmed: false,
        location_enrichments_confirmed: false,
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
        error instanceof Error ? error.message : `Workflow validation failed: ${String(error)}`,
    });
    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      error: error instanceof Error ? error.message : `Workflow validation failed: ${String(error)}`,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: false,
        brand_discoveries_confirmed: false,
        location_enrichments_confirmed: false,
      },
    };
  }

  const stepReferenceMap = getStepReferenceMap(payload.step_results);

  logger.info("enigma-smb-discovery workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    prompt: normalizedPrompt,
    brand_limit: payload.brand_limit ?? 10,
    enrich_card_revenue: payload.enrich_card_revenue ?? false,
    enrich_locations: payload.enrich_locations ?? false,
  });

  // -----------------------------------------------------------------------
  // Step 1: Brand Discovery
  // -----------------------------------------------------------------------
  const step1Ref = stepReferenceMap.get(1);
  if (!step1Ref) {
    return failWorkflow({
      client,
      pipelineRunId: payload.pipeline_run_id,
      cumulativeContext,
      executedSteps,
      message: "Missing step_result mapping for position 1",
    });
  }

  await markStepResultRunning(client, {
    stepResultId: step1Ref.step_result_id,
    inputPayload: cumulativeContext,
  });

  let discoveryResult: OperationExecutionResult;
  try {
    discoveryResult = await executeOperation(client, BRAND_DISCOVERY_OPERATION_ID, "company", {
      prompt: normalizedPrompt,
      state: payload.geography_state,
      city: payload.geography_city,
      limit: payload.brand_limit ?? 10,
    });
  } catch (error) {
    return failWorkflow({
      client,
      pipelineRunId: payload.pipeline_run_id,
      stepReference: step1Ref,
      cumulativeContext,
      executedSteps,
      message: error instanceof Error
        ? `Brand discovery failed: ${error.message}`
        : `Brand discovery failed: ${String(error)}`,
    });
  }

  const discoveryOutput = isRecord(discoveryResult.output) ? discoveryResult.output : {};
  cumulativeContext = mergeStepOutput(cumulativeContext, discoveryOutput);

  const brands = Array.isArray(discoveryOutput.brands)
    ? (discoveryOutput.brands as Array<Record<string, unknown>>)
    : [];

  if (brands.length === 0) {
    // No brands found — mark as succeeded (not_found) and skip enrichment
    await markStepResultSucceeded(client, {
      stepResultId: step1Ref.step_result_id,
      operationResult: discoveryResult,
      cumulativeContext,
    });
    executedSteps.push({
      step_position: 1,
      operation_id: BRAND_DISCOVERY_OPERATION_ID,
      status: "succeeded",
      operation_status: "not_found",
    });

    // Skip steps 2 and 3
    const step2Ref = stepReferenceMap.get(2);
    const step3Ref = stepReferenceMap.get(3);
    if (step2Ref) {
      await markStepResultSkipped(client, {
        stepResultId: step2Ref.step_result_id,
        inputPayload: cumulativeContext,
        skipReason: "no_brands_discovered",
      });
      executedSteps.push({ step_position: 2, operation_id: CARD_REVENUE_OPERATION_ID, status: "skipped" });
    }
    if (step3Ref) {
      await markStepResultSkipped(client, {
        stepResultId: step3Ref.step_result_id,
        inputPayload: cumulativeContext,
        skipReason: "no_brands_discovered",
      });
      executedSteps.push({ step_position: 3, operation_id: LOCATIONS_OPERATION_ID, status: "skipped" });
    }

    await markPipelineRunSucceeded(client, payload.pipeline_run_id);

    // Persist entity state (even with no brands, pipeline context is worth recording)
    const persistenceOutcome = await persistResults({
      client,
      payload,
      cumulativeContext,
      brands: [],
      hasLocations: false,
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "succeeded",
      cumulative_context: cumulativeContext,
      entity_id: persistenceOutcome.entityId,
      last_operation_id: BRAND_DISCOVERY_OPERATION_ID,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: persistenceOutcome.entityStateConfirmed,
        brand_discoveries_confirmed: true,
        location_enrichments_confirmed: true,
      },
    };
  }

  // Brands found — mark step 1 succeeded
  await markStepResultSucceeded(client, {
    stepResultId: step1Ref.step_result_id,
    operationResult: discoveryResult,
    cumulativeContext,
  });
  executedSteps.push({
    step_position: 1,
    operation_id: BRAND_DISCOVERY_OPERATION_ID,
    status: "succeeded",
    operation_status: discoveryResult.status,
  });

  // -----------------------------------------------------------------------
  // Step 2: Per-Brand Card Revenue (conditional)
  // -----------------------------------------------------------------------
  const step2Ref = stepReferenceMap.get(2);
  if (!step2Ref) {
    return failWorkflow({
      client,
      pipelineRunId: payload.pipeline_run_id,
      cumulativeContext,
      executedSteps,
      message: "Missing step_result mapping for position 2",
    });
  }

  if (payload.enrich_card_revenue && brands.length > 0) {
    await markStepResultRunning(client, {
      stepResultId: step2Ref.step_result_id,
      inputPayload: cumulativeContext,
    });

    let cardRevenueFailCount = 0;
    for (const brand of brands) {
      const brandId = typeof brand.enigma_brand_id === "string" ? brand.enigma_brand_id : undefined;
      const brandName = typeof brand.brand_name === "string" ? brand.brand_name : undefined;
      const brandWebsite = typeof brand.website === "string" ? brand.website : undefined;

      if (!brandId && !brandName && !brandWebsite) {
        cardRevenueFailCount += 1;
        continue;
      }

      try {
        const cardResult = await executeOperation(client, CARD_REVENUE_OPERATION_ID, "company", {
          enigma_brand_id: brandId,
          company_name: brandName,
          company_domain: brandWebsite,
        });

        if (isRecord(cardResult.output)) {
          // Merge card revenue data back into the brand object
          brand.annual_card_revenue = cardResult.output.annual_card_revenue;
          brand.annual_card_revenue_yoy_growth = cardResult.output.annual_card_revenue_yoy_growth;
          brand.annual_avg_daily_customers = cardResult.output.annual_avg_daily_customers;
          brand.annual_transaction_count = cardResult.output.annual_transaction_count;
          brand.monthly_revenue = cardResult.output.monthly_revenue;
        }
      } catch (error) {
        logger.warn("Per-brand card revenue failed, skipping brand", {
          enigma_brand_id: brandId,
          error: error instanceof Error ? error.message : String(error),
        });
        cardRevenueFailCount += 1;
      }
    }

    // Update cumulative context with enriched brands
    cumulativeContext = mergeStepOutput(cumulativeContext, { brands });

    if (cardRevenueFailCount === brands.length) {
      await markStepResultFailed(client, {
        stepResultId: step2Ref.step_result_id,
        inputPayload: cumulativeContext,
        errorMessage: "All per-brand card revenue calls failed",
      });
      executedSteps.push({ step_position: 2, operation_id: CARD_REVENUE_OPERATION_ID, status: "failed" });
    } else {
      await markStepResultSucceeded(client, {
        stepResultId: step2Ref.step_result_id,
        operationResult: {
          run_id: `${CARD_REVENUE_OPERATION_ID}:batch`,
          operation_id: CARD_REVENUE_OPERATION_ID,
          status: "found",
          output: { brands_enriched: brands.length - cardRevenueFailCount, brands_failed: cardRevenueFailCount },
        },
        cumulativeContext,
      });
      executedSteps.push({
        step_position: 2,
        operation_id: CARD_REVENUE_OPERATION_ID,
        status: "succeeded",
        operation_status: "found",
      });
    }
  } else {
    await markStepResultSkipped(client, {
      stepResultId: step2Ref.step_result_id,
      inputPayload: cumulativeContext,
      skipReason: payload.enrich_card_revenue ? "no_brands_discovered" : "enrichment_not_requested",
    });
    executedSteps.push({ step_position: 2, operation_id: CARD_REVENUE_OPERATION_ID, status: "skipped" });
  }

  // -----------------------------------------------------------------------
  // Step 3: Per-Brand Location Enrichment (conditional)
  // -----------------------------------------------------------------------
  const step3Ref = stepReferenceMap.get(3);
  if (!step3Ref) {
    return failWorkflow({
      client,
      pipelineRunId: payload.pipeline_run_id,
      cumulativeContext,
      executedSteps,
      message: "Missing step_result mapping for position 3",
    });
  }

  let hasLocations = false;
  if (payload.enrich_locations && brands.length > 0) {
    await markStepResultRunning(client, {
      stepResultId: step3Ref.step_result_id,
      inputPayload: cumulativeContext,
    });

    let locationFailCount = 0;
    for (const brand of brands) {
      const brandId = typeof brand.enigma_brand_id === "string" ? brand.enigma_brand_id : undefined;
      if (!brandId) {
        locationFailCount += 1;
        continue;
      }

      try {
        const locResult = await executeOperation(client, LOCATIONS_OPERATION_ID, "company", {
          enigma_brand_id: brandId,
          step_config: { limit: payload.location_limit ?? 5 },
          options: {
            include_card_transactions: payload.include_location_card_transactions ?? false,
            include_ranks: payload.include_location_ranks ?? false,
            include_reviews: payload.include_location_reviews ?? false,
            include_roles: payload.include_location_roles ?? false,
          },
        });

        if (isRecord(locResult.output)) {
          const locations = locResult.output.locations;
          if (Array.isArray(locations) && locations.length > 0) {
            brand.locations = locations;
            hasLocations = true;
          }
        }
      } catch (error) {
        logger.warn("Per-brand location enrichment failed, skipping brand", {
          enigma_brand_id: brandId,
          error: error instanceof Error ? error.message : String(error),
        });
        locationFailCount += 1;
      }
    }

    cumulativeContext = mergeStepOutput(cumulativeContext, { brands });

    if (locationFailCount === brands.length) {
      await markStepResultFailed(client, {
        stepResultId: step3Ref.step_result_id,
        inputPayload: cumulativeContext,
        errorMessage: "All per-brand location enrichment calls failed",
      });
      executedSteps.push({ step_position: 3, operation_id: LOCATIONS_OPERATION_ID, status: "failed" });
    } else {
      await markStepResultSucceeded(client, {
        stepResultId: step3Ref.step_result_id,
        operationResult: {
          run_id: `${LOCATIONS_OPERATION_ID}:batch`,
          operation_id: LOCATIONS_OPERATION_ID,
          status: "found",
          output: { brands_enriched: brands.length - locationFailCount, brands_failed: locationFailCount },
        },
        cumulativeContext,
      });
      executedSteps.push({
        step_position: 3,
        operation_id: LOCATIONS_OPERATION_ID,
        status: "succeeded",
        operation_status: "found",
      });
    }
  } else {
    await markStepResultSkipped(client, {
      stepResultId: step3Ref.step_result_id,
      inputPayload: cumulativeContext,
      skipReason: payload.enrich_locations ? "no_brands_discovered" : "enrichment_not_requested",
    });
    executedSteps.push({ step_position: 3, operation_id: LOCATIONS_OPERATION_ID, status: "skipped" });
  }

  // -----------------------------------------------------------------------
  // Step 4: Persistence (confirmed writes)
  // -----------------------------------------------------------------------
  await markPipelineRunSucceeded(client, payload.pipeline_run_id);

  const persistenceOutcome = await persistResults({
    client,
    payload,
    cumulativeContext,
    brands,
    hasLocations,
  });

  if (!persistenceOutcome.entityStateConfirmed || !persistenceOutcome.brandDiscoveriesConfirmed) {
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
      last_operation_id: hasLocations ? LOCATIONS_OPERATION_ID : BRAND_DISCOVERY_OPERATION_ID,
      error: message,
      executed_steps: executedSteps,
      persistence: {
        entity_state_confirmed: persistenceOutcome.entityStateConfirmed,
        brand_discoveries_confirmed: persistenceOutcome.brandDiscoveriesConfirmed,
        location_enrichments_confirmed: persistenceOutcome.locationEnrichmentsConfirmed,
      },
    };
  }

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    entity_id: persistenceOutcome.entityId,
    last_operation_id: hasLocations ? LOCATIONS_OPERATION_ID : BRAND_DISCOVERY_OPERATION_ID,
    executed_steps: executedSteps,
    persistence: {
      entity_state_confirmed: true,
      brand_discoveries_confirmed: true,
      location_enrichments_confirmed: persistenceOutcome.locationEnrichmentsConfirmed,
    },
  };
}

export const __testables = {
  ENIGMA_SMB_DISCOVERY_STEPS,
  validateWorkflowStepReferences,
};
