import { logger } from "@trigger.dev/sdk/v3";

import type { CompanyEnrichmentWorkflowPayload } from "./company-enrichment.js";
import { normalizeCompanyDomain, WorkflowContext } from "./context.js";
import type { CompanyIntelBriefingWorkflowPayload } from "./company-intel-briefing.js";
import type { EnigmaSmBDiscoveryWorkflowPayload } from "./enigma-smb-discovery.js";
import { createInternalApiClient, InternalApiClient } from "./internal-api.js";
import type { IcpJobTitlesDiscoveryWorkflowPayload } from "./icp-job-titles-discovery.js";
import type { JobPostingDiscoveryWorkflowPayload } from "./job-posting-discovery.js";
import type { PersonIntelBriefingWorkflowPayload } from "./person-intel-briefing.js";
import type { PersonSearchEnrichmentWorkflowPayload } from "./person-search-enrichment.js";
import type { TamBuildingWorkflowPayload } from "./tam-building.js";
import type { WorkflowStepReference } from "./lineage.js";

export interface PipelineRunRouterPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  api_url?: string;
  internal_api_key?: string;
}

type SupportedRouteKey =
  | "tam-building"
  | "job-posting-discovery"
  | "company-enrichment"
  | "person-search-enrichment"
  | "icp-job-titles-discovery"
  | "company-intel-briefing"
  | "person-intel-briefing"
  | "enigma-smb-discovery";

type StepConfig = Record<string, unknown>;

interface InternalBlueprintStep {
  position: number;
  operation_id?: string | null;
  step_config?: StepConfig | null;
  condition?: Record<string, unknown> | null;
  fan_out?: boolean;
  is_enabled?: boolean;
}

interface InternalStepResult {
  id: string;
  step_position: number;
  status?: string;
}

interface InternalPipelineRun {
  id: string;
  status?: "queued" | "running" | "succeeded" | "failed" | "canceled";
  org_id: string;
  company_id: string;
  submission_id: string;
  blueprint_snapshot: {
    blueprint?: Record<string, unknown>;
    steps?: InternalBlueprintStep[];
    entity?: {
      entity_type?: "company" | "person" | "job";
      input?: Record<string, unknown>;
      index?: number;
    };
    fan_out?: {
      parent_pipeline_run_id?: string;
      start_from_position?: number;
    };
  };
  step_results: InternalStepResult[];
}

interface TriggerHandle {
  id: string;
}

interface TriggerOptions {
  idempotencyKey: string;
}

type TriggerDispatcher<TPayload> = (
  payload: TPayload,
  options: TriggerOptions,
) => Promise<TriggerHandle>;

export interface PipelineRunRouterDispatchers {
  tamBuilding: TriggerDispatcher<TamBuildingWorkflowPayload>;
  jobPostingDiscovery: TriggerDispatcher<JobPostingDiscoveryWorkflowPayload>;
  companyEnrichment: TriggerDispatcher<CompanyEnrichmentWorkflowPayload>;
  personSearchEnrichment: TriggerDispatcher<PersonSearchEnrichmentWorkflowPayload>;
  icpJobTitlesDiscovery: TriggerDispatcher<IcpJobTitlesDiscoveryWorkflowPayload>;
  companyIntelBriefing: TriggerDispatcher<CompanyIntelBriefingWorkflowPayload>;
  personIntelBriefing: TriggerDispatcher<PersonIntelBriefingWorkflowPayload>;
  enigmaSmBDiscovery: TriggerDispatcher<EnigmaSmBDiscoveryWorkflowPayload>;
  runPipeline: TriggerDispatcher<PipelineRunRouterPayload>;
}

export interface PipelineRunRouterDependencies {
  client?: InternalApiClient;
  dispatchers: PipelineRunRouterDispatchers;
}

export interface PipelineRunRouterResult {
  pipeline_run_id: string;
  routed_task_id: string;
  route_key: SupportedRouteKey | "run-pipeline";
  used_fallback: boolean;
  trigger_run_id: string;
  matched_operations: string[];
}

type RoutePayload =
  | TamBuildingWorkflowPayload
  | JobPostingDiscoveryWorkflowPayload
  | CompanyEnrichmentWorkflowPayload
  | PersonSearchEnrichmentWorkflowPayload
  | IcpJobTitlesDiscoveryWorkflowPayload
  | CompanyIntelBriefingWorkflowPayload
  | PersonIntelBriefingWorkflowPayload
  | EnigmaSmBDiscoveryWorkflowPayload;

interface ResolvedRoute {
  routeKey: SupportedRouteKey;
  taskId: string;
  payload: RoutePayload;
}

interface RouteCandidate {
  routeKey: SupportedRouteKey;
  taskId: string;
  operationIds: readonly string[];
  isSupportedShape: (steps: InternalBlueprintStep[]) => boolean;
  buildPayload: (params: {
    routerPayload: PipelineRunRouterPayload;
    run: InternalPipelineRun;
    context: WorkflowContext;
    steps: InternalBlueprintStep[];
    stepResults: WorkflowStepReference[];
  }) => RoutePayload | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getClient(
  payload: PipelineRunRouterPayload,
  dependencies: PipelineRunRouterDependencies,
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

function isInternalPipelineRun(value: unknown): value is InternalPipelineRun {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.org_id === "string" &&
    typeof value.company_id === "string" &&
    typeof value.submission_id === "string" &&
    isRecord(value.blueprint_snapshot) &&
    Array.isArray(value.step_results)
  );
}

async function fetchPipelineRun(
  client: InternalApiClient,
  pipelineRunId: string,
): Promise<InternalPipelineRun> {
  return client.post<InternalPipelineRun>(
    "/api/internal/pipeline-runs/get",
    { pipeline_run_id: pipelineRunId },
    {
      validate: (data) => isInternalPipelineRun(data) && data.id === pipelineRunId,
      validationErrorMessage: `Invalid pipeline run payload for ${pipelineRunId}`,
    },
  );
}

function getExecutionStartPosition(run: InternalPipelineRun): number {
  const start = run.blueprint_snapshot.fan_out?.start_from_position;
  return typeof start === "number" && Number.isFinite(start) && start > 0 ? Math.trunc(start) : 1;
}

function getRemainingEnabledSteps(run: InternalPipelineRun): InternalBlueprintStep[] {
  const startFromPosition = getExecutionStartPosition(run);
  const steps = Array.isArray(run.blueprint_snapshot.steps) ? run.blueprint_snapshot.steps : [];

  return steps
    .filter((step) => typeof step.position === "number" && step.position >= startFromPosition)
    .filter((step) => step.is_enabled !== false)
    .sort((left, right) => left.position - right.position);
}

function getOperationSequence(steps: InternalBlueprintStep[]): string[] {
  const operationIds: string[] = [];

  for (const step of steps) {
    if (typeof step.operation_id !== "string" || step.operation_id.trim().length === 0) {
      return [];
    }
    operationIds.push(step.operation_id);
  }

  return operationIds;
}

function configsOnlyUseAllowedKeys(config: unknown, allowedKeys: readonly string[]): boolean {
  if (config == null) {
    return true;
  }
  if (!isRecord(config)) {
    return false;
  }

  return Object.keys(config).every((key) => allowedKeys.includes(key));
}

function conditionIsEmpty(condition: unknown): boolean {
  return condition == null || (isRecord(condition) && Object.keys(condition).length === 0);
}

function normalizeDomain(value: unknown): string | undefined {
  if (typeof value !== "string" || value.trim().length === 0) {
    return undefined;
  }

  try {
    return normalizeCompanyDomain(value);
  } catch {
    return undefined;
  }
}

function getOptionalString(context: WorkflowContext, keys: readonly string[]): string | undefined {
  for (const key of keys) {
    const value = context[key];
    if (typeof value === "string" && value.trim().length > 0) {
      return value.trim();
    }
  }

  return undefined;
}

function getRequiredString(context: WorkflowContext, keys: readonly string[]): string | null {
  return getOptionalString(context, keys) ?? null;
}

function getOptionalDomain(context: WorkflowContext, keys: readonly string[]): string | undefined {
  for (const key of keys) {
    const normalized = normalizeDomain(context[key]);
    if (normalized) {
      return normalized;
    }
  }

  return undefined;
}

function getRequiredDomain(context: WorkflowContext, keys: readonly string[]): string | null {
  return getOptionalDomain(context, keys) ?? null;
}

function getNormalizedStepReferences(
  run: InternalPipelineRun,
  steps: InternalBlueprintStep[],
): WorkflowStepReference[] | null {
  const stepResultsByPosition = new Map<number, InternalStepResult>();

  for (const stepResult of run.step_results) {
    if (typeof stepResult.step_position === "number" && typeof stepResult.id === "string") {
      stepResultsByPosition.set(stepResult.step_position, stepResult);
    }
  }

  const normalizedReferences: WorkflowStepReference[] = [];
  for (let index = 0; index < steps.length; index += 1) {
    const step = steps[index];
    const stepResult = stepResultsByPosition.get(step.position);
    if (!stepResult) {
      return null;
    }

    normalizedReferences.push({
      step_result_id: stepResult.id,
      step_position: index + 1,
    });
  }

  return normalizedReferences;
}

function getEntityInput(run: InternalPipelineRun): WorkflowContext {
  const rawInput = run.blueprint_snapshot.entity?.input;
  return isRecord(rawInput) ? { ...rawInput } : {};
}

function getNumberConfig(config: unknown, keys: readonly string[]): number | undefined {
  if (!isRecord(config)) {
    return undefined;
  }

  for (const key of keys) {
    const value = config[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.trunc(value);
    }
  }

  return undefined;
}

function getBooleanConfig(config: unknown, keys: readonly string[]): boolean | undefined {
  if (!isRecord(config)) {
    return undefined;
  }

  for (const key of keys) {
    const value = config[key];
    if (typeof value === "boolean") {
      return value;
    }
  }

  return undefined;
}

function getUnknownConfig<TValue>(
  config: unknown,
  keys: readonly string[],
  predicate: (value: unknown) => value is TValue,
): TValue | undefined {
  if (!isRecord(config)) {
    return undefined;
  }

  for (const key of keys) {
    const value = config[key];
    if (predicate(value)) {
      return value;
    }
  }

  return undefined;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

const ROUTES: RouteCandidate[] = [
  {
    routeKey: "tam-building",
    taskId: "tam-building",
    operationIds: ["company.search.blitzapi"],
    isSupportedShape: (steps) =>
      steps.every(
        (step) =>
          step.fan_out !== true &&
          conditionIsEmpty(step.condition) &&
          configsOnlyUseAllowedKeys(step.step_config, [
            "max_results",
            "search_page_size",
            "company_batch_size",
            "poll_interval_ms",
            "person_max_people",
            "per_person_concurrency",
            "include_work_history",
          ]),
      ),
    buildPayload: ({ routerPayload, run, context, steps, stepResults }) => ({
      pipeline_run_id: routerPayload.pipeline_run_id,
      org_id: routerPayload.org_id,
      company_id: routerPayload.company_id,
      submission_id: run.submission_id,
      step_results: stepResults,
      initial_context: context,
      search_page_size: getNumberConfig(steps[0]?.step_config, ["search_page_size", "max_results"]),
      company_batch_size: getNumberConfig(steps[0]?.step_config, ["company_batch_size"]),
      poll_interval_ms: getNumberConfig(steps[0]?.step_config, ["poll_interval_ms"]),
      person_max_people: getNumberConfig(steps[0]?.step_config, ["person_max_people"]),
      per_person_concurrency: getNumberConfig(steps[0]?.step_config, ["per_person_concurrency"]),
      include_work_history: getBooleanConfig(steps[0]?.step_config, ["include_work_history"]),
      api_url: routerPayload.api_url,
      internal_api_key: routerPayload.internal_api_key,
    }),
  },
  {
    routeKey: "job-posting-discovery",
    taskId: "job-posting-discovery",
    operationIds: ["job.search"],
    isSupportedShape: (steps) => steps.every((step) => step.fan_out !== true && conditionIsEmpty(step.condition)),
    buildPayload: ({ routerPayload, run, context, steps, stepResults }) => ({
      pipeline_run_id: routerPayload.pipeline_run_id,
      org_id: routerPayload.org_id,
      company_id: routerPayload.company_id,
      submission_id: run.submission_id,
      step_results: stepResults,
      initial_context: {
        ...(isRecord(steps[0]?.step_config) ? (steps[0]?.step_config as WorkflowContext) : {}),
        ...context,
      },
      search_page_size: getNumberConfig(steps[0]?.step_config, ["search_page_size", "limit"]),
      company_batch_size: getNumberConfig(steps[0]?.step_config, ["company_batch_size"]),
      poll_interval_ms: getNumberConfig(steps[0]?.step_config, ["poll_interval_ms"]),
      per_person_concurrency: getNumberConfig(steps[0]?.step_config, ["per_person_concurrency"]),
      api_url: routerPayload.api_url,
      internal_api_key: routerPayload.internal_api_key,
    }),
  },
  {
    routeKey: "company-enrichment",
    taskId: "company-enrichment",
    operationIds: ["company.enrich.profile", "company.research.infer_linkedin_url"],
    isSupportedShape: (steps) =>
      steps.every(
        (step) =>
          step.fan_out !== true &&
          conditionIsEmpty(step.condition) &&
          configsOnlyUseAllowedKeys(step.step_config, []),
      ),
    buildPayload: ({ routerPayload, context, stepResults }) => {
      const companyDomain = getRequiredDomain(context, ["company_domain", "canonical_domain", "domain"]);
      if (!companyDomain) {
        return null;
      }

      return {
        pipeline_run_id: routerPayload.pipeline_run_id,
        org_id: routerPayload.org_id,
        company_id: routerPayload.company_id,
        company_domain: companyDomain,
        step_results: stepResults,
        initial_context: context,
        api_url: routerPayload.api_url,
        internal_api_key: routerPayload.internal_api_key,
      };
    },
  },
  {
    routeKey: "person-search-enrichment",
    taskId: "person-search-enrichment",
    operationIds: ["person.search", "person.enrich.profile", "person.contact.resolve_email"],
    isSupportedShape: (steps) =>
      steps.every((step, index) => {
        if (step.fan_out === true || !conditionIsEmpty(step.condition)) {
          return false;
        }

        if (index === 0) {
          return configsOnlyUseAllowedKeys(step.step_config, ["limit", "max_results"]);
        }
        if (index === 1) {
          return configsOnlyUseAllowedKeys(step.step_config, ["include_work_history"]);
        }
        return configsOnlyUseAllowedKeys(step.step_config, []);
      }),
    buildPayload: ({ routerPayload, context, steps, stepResults }) => {
      const companyDomain = getRequiredDomain(context, ["company_domain", "canonical_domain", "domain"]);
      if (!companyDomain) {
        return null;
      }

      return {
        pipeline_run_id: routerPayload.pipeline_run_id,
        org_id: routerPayload.org_id,
        company_id: routerPayload.company_id,
        company_domain: companyDomain,
        submission_id: undefined,
        step_results: stepResults,
        initial_context: context,
        max_people: getNumberConfig(steps[0]?.step_config, ["limit", "max_results"]),
        include_work_history: getBooleanConfig(steps[1]?.step_config, ["include_work_history"]),
        api_url: routerPayload.api_url,
        internal_api_key: routerPayload.internal_api_key,
      };
    },
  },
  {
    routeKey: "icp-job-titles-discovery",
    taskId: "icp-job-titles-discovery",
    operationIds: ["company.derive.icp_job_titles"],
    isSupportedShape: (steps) =>
      steps.every(
        (step) =>
          step.fan_out !== true &&
          conditionIsEmpty(step.condition) &&
          configsOnlyUseAllowedKeys(step.step_config, ["processor"]),
      ),
    buildPayload: ({ routerPayload, context, steps, stepResults }) => {
      const companyDomain = getRequiredDomain(context, ["company_domain", "canonical_domain", "domain"]);
      if (!companyDomain) {
        return null;
      }

      return {
        pipeline_run_id: routerPayload.pipeline_run_id,
        org_id: routerPayload.org_id,
        company_id: routerPayload.company_id,
        company_domain: companyDomain,
        step_results: stepResults,
        initial_context: context,
        company_name: getOptionalString(context, ["company_name", "canonical_name"]),
        company_description: getOptionalString(context, ["company_description", "description"]),
        processor: getOptionalString(
          steps[0]?.step_config as WorkflowContext,
          ["processor"],
        ),
        api_url: routerPayload.api_url,
        internal_api_key: routerPayload.internal_api_key,
      };
    },
  },
  {
    routeKey: "company-intel-briefing",
    taskId: "company-intel-briefing",
    operationIds: ["company.derive.intel_briefing"],
    isSupportedShape: (steps) =>
      steps.every(
        (step) =>
          step.fan_out !== true &&
          conditionIsEmpty(step.condition) &&
          configsOnlyUseAllowedKeys(step.step_config, ["processor"]),
      ),
    buildPayload: ({ routerPayload, context, steps, stepResults }) => {
      const companyDomain = getRequiredDomain(context, [
        "company_domain",
        "canonical_domain",
        "domain",
        "target_company_domain",
      ]);
      const clientCompanyName = getRequiredString(context, ["client_company_name"]);
      const clientCompanyDomain = getRequiredDomain(context, ["client_company_domain"]);
      const clientCompanyDescription = getRequiredString(context, ["client_company_description"]);

      if (!companyDomain || !clientCompanyName || !clientCompanyDomain || !clientCompanyDescription) {
        return null;
      }

      return {
        pipeline_run_id: routerPayload.pipeline_run_id,
        org_id: routerPayload.org_id,
        company_id: routerPayload.company_id,
        company_domain: companyDomain,
        client_company_name: clientCompanyName,
        client_company_domain: clientCompanyDomain,
        client_company_description: clientCompanyDescription,
        step_results: stepResults,
        initial_context: context,
        company_name: getOptionalString(context, ["company_name", "target_company_name", "canonical_name"]),
        company_description: getOptionalString(context, [
          "company_description",
          "target_company_description",
          "description",
        ]),
        company_industry: getOptionalString(context, ["company_industry", "industry"]),
        company_size: getOptionalString(context, ["company_size", "employee_count_range"]),
        company_funding: getOptionalString(context, ["company_funding", "funding_stage"]),
        company_competitors: getUnknownConfig(
          context,
          ["company_competitors", "target_company_competitors"],
          (value): value is string | string[] => typeof value === "string" || isStringArray(value),
        ),
        processor: getOptionalString(steps[0]?.step_config as WorkflowContext, ["processor"]),
        api_url: routerPayload.api_url,
        internal_api_key: routerPayload.internal_api_key,
      };
    },
  },
  {
    routeKey: "person-intel-briefing",
    taskId: "person-intel-briefing",
    operationIds: ["person.derive.intel_briefing"],
    isSupportedShape: (steps) =>
      steps.every(
        (step) =>
          step.fan_out !== true &&
          conditionIsEmpty(step.condition) &&
          configsOnlyUseAllowedKeys(step.step_config, ["processor"]),
      ),
    buildPayload: ({ routerPayload, context, steps, stepResults }) => {
      const personFullName = getRequiredString(context, ["person_full_name", "full_name"]);
      const personCurrentCompanyName = getRequiredString(context, [
        "person_current_company_name",
        "current_company_name",
      ]);
      const clientCompanyName = getRequiredString(context, ["client_company_name"]);
      const clientCompanyDomain = getRequiredDomain(context, ["client_company_domain"]);
      const clientCompanyDescription = getRequiredString(context, ["client_company_description"]);

      if (
        !personFullName ||
        !personCurrentCompanyName ||
        !clientCompanyName ||
        !clientCompanyDomain ||
        !clientCompanyDescription
      ) {
        return null;
      }

      return {
        pipeline_run_id: routerPayload.pipeline_run_id,
        org_id: routerPayload.org_id,
        company_id: routerPayload.company_id,
        person_full_name: personFullName,
        person_linkedin_url: getOptionalString(context, ["person_linkedin_url", "linkedin_url"]),
        person_current_job_title: getOptionalString(context, [
          "person_current_job_title",
          "person_current_title",
          "current_title",
          "title",
        ]),
        person_current_company_name: personCurrentCompanyName,
        person_current_company_domain: getOptionalDomain(context, [
          "person_current_company_domain",
          "current_company_domain",
        ]),
        person_current_company_description: getOptionalString(context, [
          "person_current_company_description",
          "current_company_description",
        ]),
        client_company_name: clientCompanyName,
        client_company_domain: clientCompanyDomain,
        client_company_description: clientCompanyDescription,
        customer_company_name: getOptionalString(context, ["customer_company_name"]),
        customer_company_domain: getOptionalDomain(context, ["customer_company_domain"]),
        step_results: stepResults,
        initial_context: context,
        processor: getOptionalString(steps[0]?.step_config as WorkflowContext, ["processor"]),
        api_url: routerPayload.api_url,
        internal_api_key: routerPayload.internal_api_key,
      };
    },
  },
  {
    routeKey: "enigma-smb-discovery",
    taskId: "enigma-smb-discovery",
    operationIds: ["company.search.enigma.brands", "company.enrich.card_revenue", "company.enrich.locations"],
    isSupportedShape: (steps) =>
      steps.every(
        (step) =>
          step.fan_out !== true &&
          configsOnlyUseAllowedKeys(step.step_config, [
            "prompt",
            "geography_state",
            "geography_city",
            "brand_limit",
            "enrich_card_revenue",
            "enrich_locations",
            "location_limit",
            "include_location_card_transactions",
            "include_location_ranks",
            "include_location_reviews",
            "include_location_roles",
          ]),
      ),
    buildPayload: ({ routerPayload, run, context, steps, stepResults }) => {
      const prompt = getOptionalString(context, ["prompt"]) ??
        getOptionalString(steps[0]?.step_config as WorkflowContext, ["prompt"]);
      if (!prompt) return null;

      const firstStepConfig = (steps[0]?.step_config ?? {}) as WorkflowContext;

      return {
        pipeline_run_id: routerPayload.pipeline_run_id,
        org_id: routerPayload.org_id,
        company_id: routerPayload.company_id,
        submission_id: run.submission_id,
        step_results: stepResults,
        initial_context: context,
        prompt,
        geography_state: getOptionalString(context, ["geography_state"]) ??
          getOptionalString(firstStepConfig, ["geography_state"]),
        geography_city: getOptionalString(context, ["geography_city"]) ??
          getOptionalString(firstStepConfig, ["geography_city"]),
        brand_limit: getNumberConfig(firstStepConfig, ["brand_limit"]),
        enrich_card_revenue: getBooleanConfig(firstStepConfig, ["enrich_card_revenue"]),
        enrich_locations: getBooleanConfig(firstStepConfig, ["enrich_locations"]),
        location_limit: getNumberConfig(firstStepConfig, ["location_limit"]),
        include_location_card_transactions: getBooleanConfig(firstStepConfig, ["include_location_card_transactions"]),
        include_location_ranks: getBooleanConfig(firstStepConfig, ["include_location_ranks"]),
        include_location_reviews: getBooleanConfig(firstStepConfig, ["include_location_reviews"]),
        include_location_roles: getBooleanConfig(firstStepConfig, ["include_location_roles"]),
        api_url: routerPayload.api_url,
        internal_api_key: routerPayload.internal_api_key,
      };
    },
  },
];

function matchesOperationSequence(
  steps: InternalBlueprintStep[],
  expectedOperationIds: readonly string[],
): boolean {
  const actualOperationIds = getOperationSequence(steps);
  if (actualOperationIds.length !== expectedOperationIds.length) {
    return false;
  }

  return expectedOperationIds.every((operationId, index) => actualOperationIds[index] === operationId);
}

function resolveDedicatedRoute(
  payload: PipelineRunRouterPayload,
  run: InternalPipelineRun,
): ResolvedRoute | null {
  const remainingSteps = getRemainingEnabledSteps(run);
  if (remainingSteps.length === 0) {
    return null;
  }

  const normalizedStepResults = getNormalizedStepReferences(run, remainingSteps);
  if (!normalizedStepResults) {
    return null;
  }

  const context = getEntityInput(run);

  for (const route of ROUTES) {
    if (!matchesOperationSequence(remainingSteps, route.operationIds)) {
      continue;
    }
    if (!route.isSupportedShape(remainingSteps)) {
      continue;
    }

    const translatedPayload = route.buildPayload({
      routerPayload: payload,
      run,
      context,
      steps: remainingSteps,
      stepResults: normalizedStepResults,
    });

    if (!translatedPayload) {
      return null;
    }

    return {
      routeKey: route.routeKey,
      taskId: route.taskId,
      payload: translatedPayload,
    };
  }

  return null;
}

async function updateTriggerRunId(
  client: InternalApiClient,
  run: InternalPipelineRun,
  triggerRunId: string,
): Promise<void> {
  await client.post(
    "/api/internal/pipeline-runs/update-status",
    {
      pipeline_run_id: run.id,
      status: run.status ?? "queued",
      trigger_run_id: triggerRunId,
    },
    {
      validate: (data) => isRecord(data) && data.id === run.id,
      validationErrorMessage: `Failed to confirm trigger_run_id update for ${run.id}`,
    },
  );
}

function getIdempotencyKey(runId: string, taskId: string): string {
  return `pipeline-run-router:${runId}:${taskId}`;
}

export async function runPipelineRouter(
  payload: PipelineRunRouterPayload,
  dependencies: PipelineRunRouterDependencies,
): Promise<PipelineRunRouterResult> {
  const client = getClient(payload, dependencies);
  const run = await fetchPipelineRun(client, payload.pipeline_run_id);
  const remainingSteps = getRemainingEnabledSteps(run);
  const matchedOperations = getOperationSequence(remainingSteps);
  const resolvedRoute = resolveDedicatedRoute(payload, run);

  if (!resolvedRoute) {
    const handle = await dependencies.dispatchers.runPipeline(payload, {
      idempotencyKey: getIdempotencyKey(run.id, "run-pipeline"),
    });
    await updateTriggerRunId(client, run, handle.id);

    logger.info("pipeline-run-router fallback", {
      pipeline_run_id: run.id,
      matched_operations: matchedOperations,
      routed_task_id: "run-pipeline",
    });

    return {
      pipeline_run_id: run.id,
      routed_task_id: "run-pipeline",
      route_key: "run-pipeline",
      used_fallback: true,
      trigger_run_id: handle.id,
      matched_operations: matchedOperations,
    };
  }

  const dispatcher = {
    "tam-building": dependencies.dispatchers.tamBuilding,
    "job-posting-discovery": dependencies.dispatchers.jobPostingDiscovery,
    "company-enrichment": dependencies.dispatchers.companyEnrichment,
    "person-search-enrichment": dependencies.dispatchers.personSearchEnrichment,
    "icp-job-titles-discovery": dependencies.dispatchers.icpJobTitlesDiscovery,
    "company-intel-briefing": dependencies.dispatchers.companyIntelBriefing,
    "person-intel-briefing": dependencies.dispatchers.personIntelBriefing,
    "enigma-smb-discovery": dependencies.dispatchers.enigmaSmBDiscovery,
  }[resolvedRoute.routeKey];

  const handle = await dispatcher(resolvedRoute.payload as never, {
    idempotencyKey: getIdempotencyKey(run.id, resolvedRoute.taskId),
  });
  await updateTriggerRunId(client, run, handle.id);

  logger.info("pipeline-run-router dispatch", {
    pipeline_run_id: run.id,
    matched_operations: matchedOperations,
    route_key: resolvedRoute.routeKey,
    routed_task_id: resolvedRoute.taskId,
  });

  return {
    pipeline_run_id: run.id,
    routed_task_id: resolvedRoute.taskId,
    route_key: resolvedRoute.routeKey,
    used_fallback: false,
    trigger_run_id: handle.id,
    matched_operations: matchedOperations,
  };
}

export const __testables = {
  ROUTES,
  getExecutionStartPosition,
  getRemainingEnabledSteps,
  getNormalizedStepReferences,
  matchesOperationSequence,
  resolveDedicatedRoute,
};
