import { logger } from "@trigger.dev/sdk/v3";

import { mergeStepOutput, normalizeCompanyDomain, WorkflowContext } from "./context.js";
import {
  createInternalApiClient,
  InternalApiClient,
  InternalApiError,
  InternalApiTimeoutError,
} from "./internal-api.js";
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
  executeOperation,
  isFailedOperationResult,
  OperationExecutionResult,
} from "./operations.js";
import { upsertEntityStateConfirmed } from "./persistence.js";

const ROOT_OPERATION_ID = "job.search";

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

interface CompanyRunOutcome {
  identity: string;
  run: InternalPipelineRunRecord;
  final_context: WorkflowContext;
}

interface JobPersistenceOutcome {
  identity: string;
  entity_id?: string;
  persisted: boolean;
  error?: string;
}

interface HiringTeamMemberSummary {
  full_name?: string;
  first_name?: string;
  linkedin_url?: string;
  role?: string;
}

export interface JobPostingDiscoveryResultItem {
  job_identity: string;
  theirstack_job_id?: number;
  job_title?: string;
  normalized_title?: string;
  company_name?: string;
  company_domain?: string;
  theirstack_company_id?: string;
  company_linkedin_url?: string;
  url?: string;
  final_url?: string;
  source_url?: string;
  date_posted?: string;
  discovered_at?: string;
  remote?: boolean;
  seniority?: string;
  hiring_team?: HiringTeamMemberSummary[];
  company_seed_identity?: string;
  company_enrichment_pipeline_run_id?: string;
  company_enrichment_status?: string;
  company_enrichment_error?: string | null;
  person_search_pipeline_run_id?: string;
  person_search_status?: string;
  person_search_error?: string | null;
  job_entity_id?: string;
  job_persisted: boolean;
  job_persistence_error?: string | null;
}

interface JobPostingDiscoveryRecord extends JobPostingDiscoveryResultItem {
  job_context: WorkflowContext;
}

interface JobPostingDiscoverySummary {
  pages_processed: number;
  jobs_discovered: number;
  unique_companies_discovered: number;
  jobs_missing_company_seed: number;
  company_runs_created: number;
  company_runs_succeeded: number;
  company_runs_failed: number;
  company_runs_skipped_duplicates: number;
  person_runs_created: number;
  person_runs_succeeded: number;
  person_runs_failed: number;
  job_entities_persisted: number;
  job_entity_persistence_failed: number;
}

export interface JobPostingDiscoveryWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  submission_id?: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;
  search_page_size?: number;
  company_batch_size?: number;
  poll_interval_ms?: number;
  per_person_concurrency?: number;
  page_retry_limit?: number;
  api_url?: string;
  internal_api_key?: string;
}

export interface JobPostingDiscoveryWorkflowResult {
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
  summary: JobPostingDiscoverySummary;
  job_results: JobPostingDiscoveryResultItem[];
}

export interface JobPostingDiscoveryWorkflowDependencies {
  client?: InternalApiClient;
  sleep?: (ms: number) => Promise<void>;
}

const ROOT_STEPS: RootWorkflowDefinitionStep[] = [{ position: 1, operationId: ROOT_OPERATION_ID }];

const COMPANY_CHILD_STEPS = [
  { position: 1, operation_id: "company.enrich.profile", step_config: {} },
  { position: 2, operation_id: "company.research.infer_linkedin_url", step_config: {} },
] as const;

const PERSON_CHILD_STEPS = [
  { position: 1, operation_id: "person.search", step_config: {} },
  { position: 2, operation_id: "person.enrich.profile", step_config: {} },
  { position: 3, operation_id: "person.contact.resolve_email", step_config: {} },
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
  payload: JobPostingDiscoveryWorkflowPayload,
  dependencies: JobPostingDiscoveryWorkflowDependencies,
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
      `Job posting discovery workflow requires ${expectedPositions.length} step_results; received ${actualPositions.length}`,
    );
  }

  if (actualPositions[0] !== expectedPositions[0]) {
    throw new Error(
      `Job posting discovery workflow step_results must match positions ${expectedPositions.join(", ")}`,
    );
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

function normalizeOptionalNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function normalizeOptionalBoolean(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const items = value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim());
  return items.length > 0 ? items : undefined;
}

function companyIdentity(seed: WorkflowContext): string {
  const companyDomain = normalizeOptionalString(seed.company_domain);
  if (companyDomain) {
    try {
      return `domain:${normalizeCompanyDomain(companyDomain)}`;
    } catch {
      return `domain:${companyDomain.toLowerCase()}`;
    }
  }

  const linkedinUrl = normalizeOptionalString(seed.company_linkedin_url);
  if (linkedinUrl) {
    return `linkedin:${linkedinUrl.replace(/\/+$/, "").toLowerCase()}`;
  }

  const companyName = normalizeOptionalString(seed.company_name);
  if (companyName) {
    return `name:${companyName.toLowerCase()}`;
  }

  return `company:${JSON.stringify(seed)}`;
}

function jobIdentity(job: WorkflowContext): string {
  const theirstackJobId = normalizeOptionalNumber(job.theirstack_job_id ?? job.job_id);
  if (theirstackJobId !== undefined) {
    return `theirstack:${theirstackJobId}`;
  }

  const jobUrl =
    normalizeOptionalString(job.url) ??
    normalizeOptionalString(job.final_url) ??
    normalizeOptionalString(job.source_url);
  if (jobUrl) {
    return `url:${jobUrl}`;
  }

  const companyDomain = normalizeOptionalString(job.company_domain);
  const jobTitle = normalizeOptionalString(job.job_title);
  const discoveredAt = normalizeOptionalString(job.discovered_at);
  return `fallback:${companyDomain ?? "unknown"}:${jobTitle ?? "unknown"}:${discoveredAt ?? "unknown"}`;
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
      name: "Dedicated Job Discovery Company Enrichment",
      entity_type: "company",
    },
    steps: COMPANY_CHILD_STEPS.map((step) => ({ ...step })),
  };
}

function buildPersonChildSnapshot(): Record<string, unknown> {
  return {
    blueprint: {
      name: "Dedicated Job Discovery Person Search Enrichment",
      entity_type: "company",
    },
    steps: PERSON_CHILD_STEPS.map((step) => ({ ...step })),
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

function sanitizeHiringTeam(value: unknown): HiringTeamMemberSummary[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const members = value
    .filter((item): item is Record<string, unknown> => isRecord(item))
    .map((item) => ({
      full_name: normalizeOptionalString(item.full_name),
      first_name: normalizeOptionalString(item.first_name),
      linkedin_url: normalizeOptionalString(item.linkedin_url),
      role: normalizeOptionalString(item.role),
    }))
    .filter(
      (item) => item.full_name !== undefined || item.linkedin_url !== undefined || item.role !== undefined,
    );

  return members.length > 0 ? members : undefined;
}

function buildCompanySeedFromJob(job: WorkflowContext): WorkflowContext | null {
  const companyObject = isRecord(job.company_object) ? job.company_object : {};
  const companyDomain =
    normalizeOptionalString(companyObject.domain) ?? normalizeOptionalString(job.company_domain);
  const companyLinkedinUrl = normalizeOptionalString(companyObject.linkedin_url);
  const companyName =
    normalizeOptionalString(companyObject.name) ?? normalizeOptionalString(job.company_name);

  if (!companyDomain && !companyLinkedinUrl && !companyName) {
    return null;
  }

  const seed: WorkflowContext = {
    entity_type: "company",
    source_providers: ["theirstack"],
  };

  if (companyDomain) {
    try {
      const normalizedDomain = normalizeCompanyDomain(companyDomain);
      seed.domain = normalizedDomain;
      seed.company_domain = normalizedDomain;
      seed.canonical_domain = normalizedDomain;
    } catch {
      seed.company_domain = companyDomain;
    }
  }

  const companyId = normalizeOptionalString(companyObject.theirstack_company_id ?? companyObject.id);
  if (companyId) {
    seed.theirstack_company_id = companyId;
  }

  if (companyName) {
    seed.company_name = companyName;
  }
  if (companyLinkedinUrl) {
    seed.company_linkedin_url = companyLinkedinUrl;
  }

  const companyDescription = normalizeOptionalString(
    companyObject.company_description ?? companyObject.long_description,
  );
  if (companyDescription) {
    seed.company_description = companyDescription;
  }

  const industry = normalizeOptionalString(companyObject.industry);
  if (industry) {
    seed.industry = industry;
  }

  const employeeCount = normalizeOptionalNumber(companyObject.employee_count);
  if (employeeCount !== undefined) {
    seed.employee_count = employeeCount;
  }

  const employeeCountRange = normalizeOptionalString(companyObject.employee_count_range);
  if (employeeCountRange) {
    seed.employee_count_range = employeeCountRange;
  }

  const annualRevenueUsd = normalizeOptionalNumber(companyObject.annual_revenue_usd);
  if (annualRevenueUsd !== undefined) {
    seed.annual_revenue_usd = annualRevenueUsd;
  }

  const totalFundingUsd = normalizeOptionalNumber(companyObject.total_funding_usd);
  if (totalFundingUsd !== undefined) {
    seed.total_funding_usd = totalFundingUsd;
  }

  const fundingStage = normalizeOptionalString(companyObject.funding_stage);
  if (fundingStage) {
    seed.funding_stage = fundingStage;
  }

  const lastFundingRoundDate = normalizeOptionalString(companyObject.last_funding_round_date);
  if (lastFundingRoundDate) {
    seed.last_funding_round_date = lastFundingRoundDate;
  }

  const technologySlugs = normalizeStringArray(companyObject.technology_slugs);
  if (technologySlugs) {
    seed.technology_slugs = technologySlugs;
  }

  return seed;
}

function buildJobPersistenceContext(job: WorkflowContext): WorkflowContext {
  const companyObject = isRecord(job.company_object) ? job.company_object : {};
  const companyDomain =
    normalizeOptionalString(job.company_domain) ?? normalizeOptionalString(companyObject.domain);
  const companyName =
    normalizeOptionalString(job.company_name) ?? normalizeOptionalString(companyObject.name);
  const companyLinkedinUrl = normalizeOptionalString(companyObject.linkedin_url);
  const hiringTeam = sanitizeHiringTeam(job.hiring_team);

  const context: WorkflowContext = {
    source_providers: ["theirstack"],
    posting_status: "active",
  };

  const theirstackJobId = normalizeOptionalNumber(job.theirstack_job_id ?? job.job_id);
  if (theirstackJobId !== undefined) {
    context.theirstack_job_id = theirstackJobId;
    context.job_id = theirstackJobId;
  }

  const jobUrl =
    normalizeOptionalString(job.url) ??
    normalizeOptionalString(job.final_url) ??
    normalizeOptionalString(job.source_url);
  if (jobUrl) {
    context.job_url = jobUrl;
  }

  const copyIfPresent = (sourceKey: string, targetKey = sourceKey) => {
    const stringValue = normalizeOptionalString(job[sourceKey]);
    if (stringValue !== undefined) {
      context[targetKey] = stringValue;
      return;
    }

    const numericValue = normalizeOptionalNumber(job[sourceKey]);
    if (numericValue !== undefined) {
      context[targetKey] = numericValue;
      return;
    }

    const booleanValue = normalizeOptionalBoolean(job[sourceKey]);
    if (booleanValue !== undefined) {
      context[targetKey] = booleanValue;
      return;
    }

    const listValue = normalizeStringArray(job[sourceKey]);
    if (listValue !== undefined) {
      context[targetKey] = listValue;
    }
  };

  copyIfPresent("job_title");
  copyIfPresent("normalized_title");
  copyIfPresent("url");
  copyIfPresent("final_url");
  copyIfPresent("source_url");
  copyIfPresent("date_posted");
  copyIfPresent("discovered_at");
  copyIfPresent("location");
  copyIfPresent("short_location");
  copyIfPresent("state_code");
  copyIfPresent("country_code");
  copyIfPresent("remote");
  copyIfPresent("hybrid");
  copyIfPresent("seniority");
  copyIfPresent("employment_statuses");
  copyIfPresent("salary_string");
  copyIfPresent("min_annual_salary_usd");
  copyIfPresent("max_annual_salary_usd");
  copyIfPresent("description");
  copyIfPresent("technology_slugs");

  if (companyName) {
    context.company_name = companyName;
  }
  if (companyDomain) {
    try {
      context.company_domain = normalizeCompanyDomain(companyDomain);
    } catch {
      context.company_domain = companyDomain;
    }
  }
  if (companyLinkedinUrl) {
    context.company_linkedin_url = companyLinkedinUrl;
  }

  const companyId = normalizeOptionalString(companyObject.theirstack_company_id ?? companyObject.id);
  if (companyId) {
    context.theirstack_company_id = companyId;
  }

  if (hiringTeam) {
    context.hiring_team = hiringTeam;
  }

  return context;
}

function buildJobResult(job: WorkflowContext): JobPostingDiscoveryRecord {
  const companySeed = buildCompanySeedFromJob(job);
  const companySeedIdentity = companySeed ? companyIdentity(companySeed) : undefined;

  return {
    job_identity: jobIdentity(job),
    theirstack_job_id: normalizeOptionalNumber(job.theirstack_job_id ?? job.job_id),
    job_title: normalizeOptionalString(job.job_title),
    normalized_title: normalizeOptionalString(job.normalized_title),
    company_name:
      normalizeOptionalString(job.company_name) ??
      normalizeOptionalString(isRecord(job.company_object) ? job.company_object.name : undefined),
    company_domain:
      normalizeOptionalString(job.company_domain) ??
      normalizeOptionalString(isRecord(job.company_object) ? job.company_object.domain : undefined),
    theirstack_company_id: normalizeOptionalString(
      isRecord(job.company_object) ? job.company_object.theirstack_company_id ?? job.company_object.id : undefined,
    ),
    company_linkedin_url: normalizeOptionalString(
      isRecord(job.company_object) ? job.company_object.linkedin_url : undefined,
    ),
    url: normalizeOptionalString(job.url),
    final_url: normalizeOptionalString(job.final_url),
    source_url: normalizeOptionalString(job.source_url),
    date_posted: normalizeOptionalString(job.date_posted),
    discovered_at: normalizeOptionalString(job.discovered_at),
    remote: normalizeOptionalBoolean(job.remote),
    seniority: normalizeOptionalString(job.seniority),
    hiring_team: sanitizeHiringTeam(job.hiring_team),
    company_seed_identity: companySeedIdentity,
    company_enrichment_status: companySeedIdentity ? "pending" : "failed",
    company_enrichment_error: companySeedIdentity ? null : "missing_company_seed",
    person_search_status: companySeedIdentity ? "pending" : "not_started",
    person_search_error: companySeedIdentity ? null : "company_enrichment_not_started",
    job_persisted: false,
    job_persistence_error: null,
    job_context: buildJobPersistenceContext(job),
  };
}

function summarizeJobResults(jobResults: JobPostingDiscoveryRecord[]): JobPostingDiscoveryResultItem[] {
  return jobResults.map(({ job_context: _jobContext, ...jobResult }) => jobResult);
}

function buildWorkflowOutput(params: {
  summary: JobPostingDiscoverySummary;
  jobResults: JobPostingDiscoveryRecord[];
}): Record<string, unknown> {
  return {
    job_posting_discovery: {
      summary: params.summary,
      job_results: summarizeJobResults(params.jobResults),
    },
  };
}

function getBackoffDelayMs(attemptNumber: number): number {
  return Math.min(1_000 * 2 ** Math.max(attemptNumber - 1, 0), 8_000);
}

function getRetryableHttpStatus(result: OperationExecutionResult): number | undefined {
  for (const attempt of result.provider_attempts ?? []) {
    if (!isRecord(attempt)) {
      continue;
    }
    const httpStatus = attempt.http_status;
    if (typeof httpStatus === "number" && (httpStatus === 429 || httpStatus >= 500)) {
      return httpStatus;
    }
  }
  return undefined;
}

function isRetryableTransportError(error: unknown): boolean {
  if (error instanceof InternalApiTimeoutError) {
    return true;
  }

  if (error instanceof InternalApiError) {
    return (
      error.statusCode === null ||
      error.statusCode === 408 ||
      error.statusCode === 429 ||
      error.statusCode === 500 ||
      error.statusCode === 502 ||
      error.statusCode === 503 ||
      error.statusCode === 504
    );
  }

  return false;
}

async function executeJobSearchPageWithRetry(params: {
  client: InternalApiClient;
  pipelineRunId: string;
  searchContext: WorkflowContext;
  pageSize: number;
  offset: number;
  maxAttempts: number;
  sleep: (ms: number) => Promise<void>;
}): Promise<OperationExecutionResult> {
  let lastFailureMessage = `job.search offset=${params.offset} failed`;

  for (let attemptNumber = 1; attemptNumber <= params.maxAttempts; attemptNumber += 1) {
    try {
      const result = await executeOperation(params.client, {
        operationId: ROOT_OPERATION_ID,
        entityType: "job",
        input: {
          step_config: {
            ...params.searchContext,
            limit: params.pageSize,
            offset: params.offset,
          },
        },
      });

      if (!isFailedOperationResult(result)) {
        return result;
      }

      const retryableHttpStatus = getRetryableHttpStatus(result);
      if (!retryableHttpStatus || attemptNumber === params.maxAttempts) {
        lastFailureMessage = retryableHttpStatus
          ? `job.search offset=${params.offset} failed with HTTP ${retryableHttpStatus}`
          : `job.search offset=${params.offset} failed with non-retryable status`;
        break;
      }

      const delayMs = getBackoffDelayMs(attemptNumber);
      logger.warn("job-posting-discovery retrying failed search page", {
        pipeline_run_id: params.pipelineRunId,
        offset: params.offset,
        attempt: attemptNumber,
        max_attempts: params.maxAttempts,
        http_status: retryableHttpStatus,
        delay_ms: delayMs,
      });
      await params.sleep(delayMs);
    } catch (error) {
      if (!isRetryableTransportError(error) || attemptNumber === params.maxAttempts) {
        lastFailureMessage =
          error instanceof Error
            ? `job.search offset=${params.offset} transport failed: ${error.message}`
            : `job.search offset=${params.offset} transport failed: ${String(error)}`;
        break;
      }

      const delayMs = getBackoffDelayMs(attemptNumber);
      logger.warn("job-posting-discovery retrying transport error", {
        pipeline_run_id: params.pipelineRunId,
        offset: params.offset,
        attempt: attemptNumber,
        max_attempts: params.maxAttempts,
        error: error instanceof Error ? error.message : String(error),
        delay_ms: delayMs,
      });
      await params.sleep(delayMs);
    }
  }

  throw new Error(lastFailureMessage);
}

export async function runJobPostingDiscoveryWorkflow(
  payload: JobPostingDiscoveryWorkflowPayload,
  dependencies: JobPostingDiscoveryWorkflowDependencies = {},
): Promise<JobPostingDiscoveryWorkflowResult> {
  const client = getClient(payload, dependencies);
  const sleep = dependencies.sleep ?? ((ms: number) => new Promise((resolve) => setTimeout(resolve, ms)));
  const searchPageSize = toBoundedInteger(payload.search_page_size, {
    fallback: 100,
    min: 1,
    max: 500,
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
  const pageRetryLimit = toBoundedInteger(payload.page_retry_limit, {
    fallback: 4,
    min: 1,
    max: 8,
  });

  validateWorkflowStepReferences(payload.step_results);

  const rootStepReference = getStepReference(payload.step_results, 1);
  const executedSteps: JobPostingDiscoveryWorkflowResult["executed_steps"] = [];
  const summary: JobPostingDiscoverySummary = {
    pages_processed: 0,
    jobs_discovered: 0,
    unique_companies_discovered: 0,
    jobs_missing_company_seed: 0,
    company_runs_created: 0,
    company_runs_succeeded: 0,
    company_runs_failed: 0,
    company_runs_skipped_duplicates: 0,
    person_runs_created: 0,
    person_runs_succeeded: 0,
    person_runs_failed: 0,
    job_entities_persisted: 0,
    job_entity_persistence_failed: 0,
  };
  const searchContext = { ...(payload.initial_context ?? {}) };
  let cumulativeContext = mergeStepOutput({}, payload.initial_context ?? {});
  const jobResults: JobPostingDiscoveryRecord[] = [];
  const jobResultsByIdentity = new Map<string, JobPostingDiscoveryRecord>();
  const companySeeds = new Map<string, WorkflowContext>();

  await markPipelineRunRunning(client, payload.pipeline_run_id);
  await markStepResultRunning(client, {
    stepResultId: rootStepReference.step_result_id,
    inputPayload: cumulativeContext,
  });

  logger.info("job-posting-discovery workflow start", {
    pipeline_run_id: payload.pipeline_run_id,
    org_id: payload.org_id,
    company_id: payload.company_id,
    submission_id: payload.submission_id,
    search_page_size: searchPageSize,
    company_batch_size: companyBatchSize,
    poll_interval_ms: pollIntervalMs,
    per_person_concurrency: perPersonConcurrency,
    page_retry_limit: pageRetryLimit,
  });

  try {
    let offset = 0;

    while (true) {
      const pageResult = await executeJobSearchPageWithRetry({
        client,
        pipelineRunId: payload.pipeline_run_id,
        searchContext,
        pageSize: searchPageSize,
        offset,
        maxAttempts: pageRetryLimit,
        sleep,
      });

      summary.pages_processed += 1;
      const output = isRecord(pageResult.output) ? pageResult.output : {};
      const rawResults = Array.isArray(output.results) ? output.results : [];
      const typedResults = rawResults.filter((job): job is WorkflowContext => isRecord(job));

      if (rawResults.length !== typedResults.length) {
        logger.warn("job-posting-discovery discarded non-object job rows", {
          pipeline_run_id: payload.pipeline_run_id,
          offset,
          discarded_count: rawResults.length - typedResults.length,
        });
      }

      for (const job of typedResults) {
        const jobResult = buildJobResult(job);
        if (jobResultsByIdentity.has(jobResult.job_identity)) {
          continue;
        }

        if (jobResult.company_seed_identity) {
          const seed = buildCompanySeedFromJob(job);
          if (seed) {
            companySeeds.set(jobResult.company_seed_identity, seed);
          }
        } else {
          summary.jobs_missing_company_seed += 1;
        }

        jobResultsByIdentity.set(jobResult.job_identity, jobResult);
        jobResults.push(jobResult);
      }

      if (typedResults.length < searchPageSize) {
        break;
      }

      offset += searchPageSize;
    }
  } catch (error) {
    const message =
      error instanceof Error
        ? `Job search pagination failed: ${error.message}`
        : `Job search pagination failed: ${String(error)}`;
    const failedOutput = buildWorkflowOutput({ summary, jobResults });
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
      job_results: summarizeJobResults(jobResults),
    };
  }

  summary.jobs_discovered = jobResults.length;
  summary.unique_companies_discovered = companySeeds.size;

  if (companySeeds.size > 0 && !payload.submission_id) {
    const message =
      "Job posting discovery workflow requires submission_id to create downstream child pipeline runs";
    const failedOutput = buildWorkflowOutput({ summary, jobResults });
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
      errorDetails: {},
    });
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
      job_results: summarizeJobResults(jobResults),
    };
  }

  const companySeedEntries = Array.from(companySeeds.entries()).map(([identity, seed]) => ({
    identity,
    seed,
  }));
  const companyLineage = new Map<
    string,
    {
      company_enrichment_pipeline_run_id?: string;
      company_enrichment_status?: string;
      company_enrichment_error?: string | null;
      person_search_pipeline_run_id?: string;
      person_search_status?: string;
      person_search_error?: string | null;
    }
  >();

  const companyBatches = chunk(companySeedEntries, companyBatchSize);
  for (const batch of companyBatches) {
    const childCreation = await createChildRuns(client, {
      parent_pipeline_run_id: payload.pipeline_run_id,
      submission_id: payload.submission_id as string,
      org_id: payload.org_id,
      company_id: payload.company_id,
      blueprint_snapshot: buildCompanyChildSnapshot(),
      child_entities: batch.map(({ seed }) => ({ ...seed })),
      start_from_position: 1,
    });

    summary.company_runs_created += childCreation.child_runs.length;
    summary.company_runs_skipped_duplicates += childCreation.skipped_duplicates_count ?? 0;

    const childRunIdentityMap = new Map<string, string>();
    for (const childRun of childCreation.child_runs) {
      const childIdentity = isRecord(childRun.entity_input)
        ? companyIdentity(childRun.entity_input)
        : undefined;
      if (childIdentity) {
        childRunIdentityMap.set(childRun.pipeline_run_id, childIdentity);
      }
    }

    const terminalCompanyRuns = await runWithConcurrencyLimit(
      childCreation.child_runs,
      Math.min(companyBatchSize, 8),
      async (childRun) =>
        waitForPipelineRunTerminal({
          client,
          pipelineRunId: childRun.pipeline_run_id,
          pollIntervalMs,
          sleep,
        }),
    );

    const successfulCompanyRuns: CompanyRunOutcome[] = [];
    for (const terminalRun of terminalCompanyRuns) {
      const identity =
        childRunIdentityMap.get(terminalRun.id) ?? companyIdentity(extractFinalContext(terminalRun));
      const finalContext = extractFinalContext(terminalRun);

      companyLineage.set(identity, {
        company_enrichment_pipeline_run_id: terminalRun.id,
        company_enrichment_status: terminalRun.status ?? "unknown",
        company_enrichment_error: terminalRun.error_message ?? null,
      });

      for (const jobResult of jobResults) {
        if (jobResult.company_seed_identity !== identity) {
          continue;
        }
        jobResult.company_enrichment_pipeline_run_id = terminalRun.id;
        jobResult.company_enrichment_status = terminalRun.status ?? "unknown";
        jobResult.company_enrichment_error = terminalRun.error_message ?? null;
      }

      if (terminalRun.status === "succeeded") {
        summary.company_runs_succeeded += 1;
        successfulCompanyRuns.push({ identity, run: terminalRun, final_context: finalContext });
      } else {
        summary.company_runs_failed += 1;
      }
    }

    const personRuns = await runWithConcurrencyLimit(
      successfulCompanyRuns,
      Math.min(perPersonConcurrency, 12),
      async (companyRun) => {
        const companyDomain = normalizeOptionalString(
          companyRun.final_context.company_domain ??
            companyRun.final_context.canonical_domain ??
            companyRun.final_context.domain,
        );
        if (!companyDomain) {
          return { identity: companyRun.identity, run: null as InternalPipelineRunRecord | null };
        }

        const creationResult = await createChildRuns(client, {
          parent_pipeline_run_id: companyRun.run.id,
          submission_id: companyRun.run.submission_id,
          org_id: payload.org_id,
          company_id: payload.company_id,
          blueprint_snapshot: buildPersonChildSnapshot(),
          child_entities: [
            {
              entity_type: "company",
              company_domain: companyDomain,
            },
          ],
          start_from_position: 1,
          parent_cumulative_context: companyRun.final_context,
        });

        summary.person_runs_created += creationResult.child_runs.length;

        const personChild = creationResult.child_runs[0];
        if (!personChild) {
          return { identity: companyRun.identity, run: null as InternalPipelineRunRecord | null };
        }

        return {
          identity: companyRun.identity,
          run: await waitForPipelineRunTerminal({
            client,
            pipelineRunId: personChild.pipeline_run_id,
            pollIntervalMs,
            sleep,
          }),
        };
      },
    );

    for (const personRun of personRuns) {
      if (!personRun.run) {
        for (const jobResult of jobResults) {
          if (jobResult.company_seed_identity !== personRun.identity) {
            continue;
          }
          jobResult.person_search_status = "failed";
          jobResult.person_search_error = "person_child_run_not_created";
        }
        summary.person_runs_failed += 1;
        continue;
      }

      const lineage = companyLineage.get(personRun.identity) ?? {};
      lineage.person_search_pipeline_run_id = personRun.run.id;
      lineage.person_search_status = personRun.run.status ?? "unknown";
      lineage.person_search_error = personRun.run.error_message ?? null;
      companyLineage.set(personRun.identity, lineage);

      for (const jobResult of jobResults) {
        if (jobResult.company_seed_identity !== personRun.identity) {
          continue;
        }
        jobResult.person_search_pipeline_run_id = personRun.run.id;
        jobResult.person_search_status = personRun.run.status ?? "unknown";
        jobResult.person_search_error = personRun.run.error_message ?? null;
      }

      if (personRun.run.status === "succeeded") {
        summary.person_runs_succeeded += 1;
      } else {
        summary.person_runs_failed += 1;
      }
    }
  }

  const preliminaryOutput = buildWorkflowOutput({ summary, jobResults });
  cumulativeContext = mergeStepOutput(cumulativeContext, preliminaryOutput);

  const hasDownstreamFailures =
    summary.jobs_missing_company_seed > 0 ||
    summary.company_runs_failed > 0 ||
    summary.person_runs_failed > 0;

  const preliminaryOperationResult = buildOperationResult({
    pipelineRunId: payload.pipeline_run_id,
    status: hasDownstreamFailures ? "failed" : summary.jobs_discovered > 0 ? "found" : "not_found",
    output: preliminaryOutput,
  });

  await markStepResultSucceeded(client, {
    stepResultId: rootStepReference.step_result_id,
    operationResult: preliminaryOperationResult,
    cumulativeContext,
  });
  await markPipelineRunSucceeded(client, payload.pipeline_run_id);

  const persistenceOutcomes = await runWithConcurrencyLimit(jobResults, 5, async (jobResult) => {
    try {
      const persisted = await upsertEntityStateConfirmed(client, {
        pipelineRunId: payload.pipeline_run_id,
        entityType: "job",
        cumulativeContext: jobResult.job_context,
        lastOperationId: ROOT_OPERATION_ID,
      });
      return {
        identity: jobResult.job_identity,
        entity_id: persisted.entity_id,
        persisted: true,
      } satisfies JobPersistenceOutcome;
    } catch (error) {
      return {
        identity: jobResult.job_identity,
        persisted: false,
        error: error instanceof Error ? error.message : String(error),
      } satisfies JobPersistenceOutcome;
    }
  });

  for (const outcome of persistenceOutcomes) {
    const jobResult = jobResultsByIdentity.get(outcome.identity);
    if (!jobResult) {
      continue;
    }

    jobResult.job_persisted = outcome.persisted;
    jobResult.job_entity_id = outcome.entity_id;
    jobResult.job_persistence_error = outcome.error ?? null;

    if (outcome.persisted) {
      summary.job_entities_persisted += 1;
    } else {
      summary.job_entity_persistence_failed += 1;
    }
  }

  const finalOutput = buildWorkflowOutput({ summary, jobResults });
  cumulativeContext = mergeStepOutput(cumulativeContext, finalOutput);
  const finalOperationResult = buildOperationResult({
    pipelineRunId: payload.pipeline_run_id,
    status:
      summary.job_entity_persistence_failed > 0 || hasDownstreamFailures
        ? "failed"
        : summary.jobs_discovered > 0
          ? "found"
          : "not_found",
    output: finalOutput,
  });

  if (summary.job_entity_persistence_failed > 0) {
    const message = `Entity state upsert failed for ${summary.job_entity_persistence_failed} job postings`;
    await markStepResultFailed(client, {
      stepResultId: rootStepReference.step_result_id,
      inputPayload: payload.initial_context ?? {},
      operationResult: finalOperationResult,
      cumulativeContext,
      errorMessage: message,
      errorDetails: {
        job_entities_persisted: summary.job_entities_persisted,
        job_entity_persistence_failed: summary.job_entity_persistence_failed,
      },
    });
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        job_entities_persisted: summary.job_entities_persisted,
        job_entity_persistence_failed: summary.job_entity_persistence_failed,
      },
    });
    if (payload.submission_id) {
      await syncSubmissionStatus(client, payload.submission_id);
    }

    executedSteps.push({
      step_position: 1,
      operation_id: ROOT_OPERATION_ID,
      status: "failed",
      operation_status: finalOperationResult.status,
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      failed_step_position: 1,
      error: message,
      executed_steps: executedSteps,
      summary,
      job_results: summarizeJobResults(jobResults),
    };
  }

  if (hasDownstreamFailures) {
    const message = "Job posting discovery completed with downstream workflow failures";
    await markStepResultFailed(client, {
      stepResultId: rootStepReference.step_result_id,
      inputPayload: payload.initial_context ?? {},
      operationResult: finalOperationResult,
      cumulativeContext,
      errorMessage: message,
      errorDetails: {
        jobs_missing_company_seed: summary.jobs_missing_company_seed,
        company_runs_failed: summary.company_runs_failed,
        person_runs_failed: summary.person_runs_failed,
      },
    });
    await markPipelineRunFailed(client, {
      pipelineRunId: payload.pipeline_run_id,
      errorMessage: message,
      errorDetails: {
        jobs_missing_company_seed: summary.jobs_missing_company_seed,
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
      operation_status: finalOperationResult.status,
    });

    return {
      pipeline_run_id: payload.pipeline_run_id,
      status: "failed",
      cumulative_context: cumulativeContext,
      failed_step_position: 1,
      error: message,
      executed_steps: executedSteps,
      summary,
      job_results: summarizeJobResults(jobResults),
    };
  }

  await markStepResultSucceeded(client, {
    stepResultId: rootStepReference.step_result_id,
    operationResult: finalOperationResult,
    cumulativeContext,
  });
  if (payload.submission_id) {
    await syncSubmissionStatus(client, payload.submission_id);
  }

  executedSteps.push({
    step_position: 1,
    operation_id: ROOT_OPERATION_ID,
    status: "succeeded",
    operation_status: finalOperationResult.status,
  });

  return {
    pipeline_run_id: payload.pipeline_run_id,
    status: "succeeded",
    cumulative_context: cumulativeContext,
    executed_steps: executedSteps,
    summary,
    job_results: summarizeJobResults(jobResults),
  };
}

export const __testables = {
  ROOT_STEPS,
  validateWorkflowStepReferences,
  buildCompanySeedFromJob,
  buildJobPersistenceContext,
  companyIdentity,
  jobIdentity,
};
