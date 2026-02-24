import { logger, task, wait } from "@trigger.dev/sdk/v3";
import { evaluateCondition } from "../utils/evaluate-condition.js";

interface RunPipelinePayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  api_url?: string;
  internal_api_key?: string;
}

interface InternalPipelineRun {
  id: string;
  org_id: string;
  company_id: string;
  submission_id: string;
  blueprint_snapshot: {
    blueprint: Record<string, unknown>;
    steps: Array<{
      id: string;
      position: number;
      operation_id?: string | null;
      step_config?: Record<string, unknown> | null;
      condition?: Record<string, unknown> | null;
      fan_out?: boolean;
      is_enabled?: boolean;
    }>;
    entity?: {
      entity_type?: "person" | "company" | "job";
      input?: Record<string, unknown>;
      index?: number;
    };
    fan_out?: {
      parent_pipeline_run_id?: string;
      start_from_position?: number;
    };
  };
  step_results: Array<{
    id: string;
    step_position: number;
    status: string;
  }>;
  submissions: {
    id: string;
    input_payload: Record<string, unknown> | unknown[];
  };
}

interface FanOutChildRunsResponse {
  parent_pipeline_run_id: string;
  child_runs: Array<{
    pipeline_run_id: string;
    pipeline_run_status: string;
    trigger_run_id?: string | null;
    entity_type?: string;
    entity_input?: Record<string, unknown>;
  }>;
  child_run_ids: string[];
  skipped_duplicates_count?: number;
  skipped_duplicate_identifiers?: string[];
}

interface ExecuteResponseEnvelope {
  data?: {
    run_id: string;
    operation_id: string;
    status: string;
    output?: Record<string, unknown> | null;
    provider_attempts?: Array<Record<string, unknown>>;
    missing_inputs?: string[];
  };
  error?: string;
}

interface FreshnessCheckResponse {
  fresh: boolean;
  entity_id?: string | null;
  last_enriched_at?: string | null;
  age_hours?: number | null;
  canonical_payload?: Record<string, unknown> | null;
}

interface InternalEnvelope<TData> {
  data?: TData;
  error?: string;
}

interface InternalConfig {
  apiUrl: string;
  internalApiKey: string;
}

interface InternalStepResult {
  id: string;
  step_position: number;
  duration_ms?: number | null;
}

interface SkipIfFreshConfig {
  maxAgeHours: number;
  identityFields: string[];
}

const ICP_JOB_TITLES_PROMPT_TEMPLATE = `CONTEXT
You are a B2B buyer persona researcher. You will be given a company name, domain, and optionally a company description. Your job is to research this company thoroughly and produce an exhaustive list of job titles that represent realistic buyers, champions, evaluators, and decision-makers for this company's product(s).

INPUTS
companyName: {company_name}
domain: {domain}
companyDescription: {company_description}

RESEARCH INSTRUCTIONS

1. Research the company
   - Visit the company website to understand what they sell, who they sell to, and how they position their product.
   - Review case studies, testimonials, and customer logos to identify real buyers and users.
   - Check G2, TrustRadius, Capterra, and similar review platforms. Look specifically at reviewer job titles.
   - Review the company's LinkedIn presence and any published ICP or buyer persona content.
   - Search: "[{company_name}] case study" "[{company_name}] customer story"
   - Capture any named roles or titles.

2. Identify the buying committee
   Determine realistic roles for:
   - **Champions** - Day-to-day users or people experiencing the problem directly. They discover, evaluate, and advocate internally.
   - **Evaluators** - Technical or operational stakeholders who run POCs or compare alternatives.
   - **Decision makers** - Budget owners and signers. Only include if appropriate for this product category and price point.

3. Generate title variations
   For each persona:
   - Include realistic seniority variants (Manager, Senior Manager, Director, Head, VP, Lead) only where appropriate.
   - Include function-specific variants where relevant (e.g., Security, Compliance, GRC, IT, Engineering, Legal, Risk).

CRITICAL GUARDRAILS
- Every title must be grounded in evidence from the company website, reviews, case studies, or known buyer patterns for this category.
- Do not guess or hallucinate titles.
- Exclude roles that would reasonably not care about or buy this product.
- Do not include generic functional labels (e.g., "Information Security").
- Quantity target: 30-60 titles. More is fine if grounded. Fewer is fine if narrow. Never pad.

OUTPUT FORMAT
companyName: {company_name}
domain: {domain}
inferredProduct: One sentence describing what the company sells and to whom, based on your research.
buyerPersonaSummary: 2-3 sentences describing the buying committee - who champions it, who evaluates it, who signs off.
titles: For each title include the title, buyerRole (champion | evaluator | decision_maker), and reasoning (one sentence grounding this title in research evidence).`;

const COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE = `#CONTEXT#
You are a B2B sales intelligence researcher. You will receive inputs about a client company (the seller) and a target company (the prospect). Your job is to produce structured, verified intelligence about the target company that the client company's sales team can use to prepare for outreach.

#INPUTS#
client_company_name: {client_company_name}
client_company_description: {client_company_description}
target_company_name: {target_company_name}
target_company_domain: {target_company_domain}
target_company_description: {target_company_description}
target_company_industry: {target_company_industry}
target_company_size: {target_company_size}
target_company_funding: {target_company_funding}
target_company_competitors:
{target_company_competitors}

#OBJECTIVE#
Produce structured intelligence about the target company that covers their business context, financial position, strategic initiatives, posture and gaps in the domain relevant to what the client company sells, operational bottlenecks the client company's product addresses, and detailed competitor profiles. All claims must be cited with source URLs. Do not fabricate specific metrics, deal details, or quotes.

#INSTRUCTIONS#
Research and populate every field in the output schema. For each field:
- Use only verifiable, publicly available information
- Cite sources with URLs
- Assign a confidence score (high/medium/low)
- If information cannot be verified, state that explicitly rather than inferring

Focus research effort on:
1. Current business status, funding, and financial metrics
2. Strategic initiatives that expand the target company's need for what the client company sells
3. Key customer relationships and concentration risk
4. Where the target company's operations create bottlenecks that the client company's product category directly addresses
5. Current certifications, capabilities, and gaps in the domain relevant to the client company's product
6. Competitor positioning — pricing, procurement advantages, and posture in the client company's domain — with specifics

## OUTPUT SCHEMA

\`\`\`json
{
  "type": "object",
  "properties": {
    "target_business_summary": {
      "type": "string",
      "description": "Overview of the target company's current business status, market position, strategic focus, key partnerships, and recent developments."
    },
    "target_financial_highlights": {
      "type": "object",
      "description": "Key financial metrics including revenue, funding, valuation, growth trajectory, and any publicly available financial data."
    },
    "target_strategic_initiatives": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "initiative": { "type": "string" },
          "description": { "type": "string" },
          "expanded_risk_surface": { "type": "string", "description": "New risks or needs this initiative creates that are relevant to what the client company sells." }
        }
      }
    },
    "target_key_customers_and_concentration_risk": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "customer_name": { "type": "string" },
          "contract_details": { "type": "string" },
          "concentration_risk_analysis": { "type": "string" }
        }
      }
    },
    "target_operational_bottlenecks": {
      "type": "string",
      "description": "Analysis of where the target company's operations create pain points or bottlenecks that the client company's product category directly addresses."
    },
    "target_relevant_posture_and_gaps": {
      "type": "string",
      "description": "Assessment of the target company's current capabilities, certifications, and gaps in the domain relevant to what the client company sells."
    },
    "competitor_profiles": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "competitor_name": { "type": "string" },
          "key_differentiators": { "type": "string" },
          "procurement_and_pricing_advantages": { "type": "string" },
          "relevant_posture": { "type": "string", "description": "How this competitor positions in the domain relevant to the client company's product." }
        }
      }
    },
    "client_strategic_relevance": {
      "type": "string",
      "description": "2-4 sentences explaining how the client company's product directly ties to the target company's chief strategic objectives, revenue goals, or critical operational needs identified in this research. Frame as what adopting the client's product unlocks for the target — in terms of revenue acceleration, risk reduction, or strategic execution."
    }
  }
}
\`\`\``;

async function executeParallelDeepResearch(
  cumulativeContext: Record<string, unknown>,
  stepConfig: Record<string, unknown>,
): Promise<NonNullable<ExecuteResponseEnvelope["data"]>> {
  const apiKey = process.env.PARALLEL_API_KEY;
  if (!apiKey) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "skipped",
          skip_reason: "missing_parallel_api_key",
        },
      ],
    };
  }

  const companyName = String(cumulativeContext.company_name || cumulativeContext.companyName || "");
  const domain = String(cumulativeContext.domain || cumulativeContext.company_domain || "");
  const companyDescription = String(
    cumulativeContext.company_description || cumulativeContext.description || "",
  );

  if (!companyName || !domain) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      missing_inputs: [
        ...(!companyName ? ["company_name"] : []),
        ...(!domain ? ["domain"] : []),
      ],
      provider_attempts: [],
    };
  }

  const prompt = ICP_JOB_TITLES_PROMPT_TEMPLATE.replaceAll("{company_name}", companyName)
    .replaceAll("{domain}", domain)
    .replaceAll("{company_description}", companyDescription || "No description provided.");

  const processor = String(stepConfig.processor || "pro");
  const maxPollAttempts = Number(stepConfig.max_poll_attempts || 90);
  const pollIntervalSeconds = Number(stepConfig.poll_interval_seconds || 20);

  const headers: Record<string, string> = {
    "x-api-key": apiKey,
    "Content-Type": "application/json",
  };

  let runId: string;
  try {
    const createResponse = await fetch("https://api.parallel.ai/v1/tasks/runs", {
      method: "POST",
      headers,
      body: JSON.stringify({ input: prompt, processor }),
    });
    if (!createResponse.ok) {
      const errorText = await createResponse.text();
      return {
        run_id: crypto.randomUUID(),
        operation_id: "company.derive.icp_job_titles",
        status: "failed",
        output: null,
        provider_attempts: [
          {
            provider: "parallel",
            action: "deep_research_icp_job_titles",
            status: "failed",
            error: `task_creation_failed: ${createResponse.status}`,
            raw_response: errorText,
          },
        ],
      };
    }
    const createData = (await createResponse.json()) as { run_id: string; status: string };
    runId = createData.run_id;
    logger.info("Parallel deep research task created", { runId, processor, companyName, domain });
  } catch (error) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "failed",
          error: `task_creation_exception: ${error instanceof Error ? error.message : String(error)}`,
        },
      ],
    };
  }

  let taskStatus = "queued";
  let pollCount = 0;

  while (taskStatus !== "completed" && taskStatus !== "failed" && pollCount < maxPollAttempts) {
    await wait.for({ seconds: pollIntervalSeconds });
    pollCount++;

    try {
      const statusResponse = await fetch(`https://api.parallel.ai/v1/tasks/runs/${runId}`, {
        method: "GET",
        headers: { "x-api-key": apiKey },
      });
      if (!statusResponse.ok) {
        logger.warn("Parallel status check returned non-OK", {
          runId,
          status: statusResponse.status,
          pollCount,
        });
        continue;
      }
      const statusData = (await statusResponse.json()) as { status: string };
      taskStatus = statusData.status;
      logger.info("Parallel deep research poll", { runId, taskStatus, pollCount });
    } catch (error) {
      logger.warn("Parallel status check exception", {
        runId,
        pollCount,
        error: error instanceof Error ? error.message : String(error),
      });
      continue;
    }
  }

  if (taskStatus === "failed") {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "failed",
          error: "parallel_task_failed",
          parallel_run_id: runId,
          poll_count: pollCount,
        },
      ],
    };
  }

  if (taskStatus !== "completed") {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "failed",
          error: "poll_timeout",
          parallel_run_id: runId,
          poll_count: pollCount,
          max_poll_attempts: maxPollAttempts,
        },
      ],
    };
  }

  try {
    const resultResponse = await fetch(`https://api.parallel.ai/v1/tasks/runs/${runId}/result`, {
      method: "GET",
      headers: { "x-api-key": apiKey },
    });
    if (!resultResponse.ok) {
      const errorText = await resultResponse.text();
      return {
        run_id: crypto.randomUUID(),
        operation_id: "company.derive.icp_job_titles",
        status: "failed",
        output: null,
        provider_attempts: [
          {
            provider: "parallel",
            action: "deep_research_icp_job_titles",
            status: "failed",
            error: `result_fetch_failed: ${resultResponse.status}`,
            raw_response: errorText,
            parallel_run_id: runId,
          },
        ],
      };
    }
    const resultData = (await resultResponse.json()) as Record<string, unknown>;
    logger.info("Parallel deep research completed", { runId, pollCount, companyName, domain });

    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "found",
      output: {
        parallel_run_id: runId,
        processor,
        company_name: companyName,
        domain,
        company_description: companyDescription,
        parallel_raw_response: resultData,
      },
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "found",
          parallel_run_id: runId,
          processor,
          poll_count: pollCount,
        },
      ],
    };
  } catch (error) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "failed",
          error: `result_fetch_exception: ${error instanceof Error ? error.message : String(error)}`,
          parallel_run_id: runId,
        },
      ],
    };
  }
}

async function executeCompanyIntelBriefing(
  cumulativeContext: Record<string, unknown>,
  stepConfig: Record<string, unknown>,
): Promise<NonNullable<ExecuteResponseEnvelope["data"]>> {
  const apiKey = process.env.PARALLEL_API_KEY;
  if (!apiKey) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_company_intel_briefing",
          status: "skipped",
          skip_reason: "missing_parallel_api_key",
        },
      ],
    };
  }

  const clientCompanyName = String(cumulativeContext.client_company_name || "");
  const clientCompanyDescription = String(cumulativeContext.client_company_description || "");
  const targetCompanyName = String(
    cumulativeContext.target_company_name || cumulativeContext.company_name || "",
  );
  const targetCompanyDomain = String(cumulativeContext.target_company_domain || cumulativeContext.domain || "");
  const targetCompanyDescription = String(
    cumulativeContext.target_company_description ||
      cumulativeContext.company_description ||
      cumulativeContext.description ||
      "",
  );
  const targetCompanyIndustry = String(cumulativeContext.target_company_industry || cumulativeContext.industry || "");
  const targetCompanySize = String(
    cumulativeContext.target_company_size ||
      cumulativeContext.employee_count ||
      cumulativeContext.employee_range ||
      "",
  );
  const targetCompanyFunding = String(cumulativeContext.target_company_funding || cumulativeContext.funding || "");
  const targetCompanyCompetitors = String(cumulativeContext.target_company_competitors || "");

  if (!clientCompanyName || !clientCompanyDescription || !targetCompanyName || !targetCompanyDomain) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "failed",
      output: null,
      missing_inputs: [
        ...(!clientCompanyName ? ["client_company_name"] : []),
        ...(!clientCompanyDescription ? ["client_company_description"] : []),
        ...(!targetCompanyName ? ["target_company_name"] : []),
        ...(!targetCompanyDomain ? ["target_company_domain"] : []),
      ],
      provider_attempts: [],
    };
  }

  const prompt = COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE.replaceAll(
    "{client_company_name}",
    clientCompanyName,
  )
    .replaceAll("{client_company_description}", clientCompanyDescription)
    .replaceAll("{target_company_name}", targetCompanyName)
    .replaceAll("{target_company_domain}", targetCompanyDomain)
    .replaceAll("{target_company_description}", targetCompanyDescription || "No description provided.")
    .replaceAll("{target_company_industry}", targetCompanyIndustry || "Not specified")
    .replaceAll("{target_company_size}", targetCompanySize || "Not specified")
    .replaceAll("{target_company_funding}", targetCompanyFunding || "Not specified")
    .replaceAll(
      "{target_company_competitors}",
      targetCompanyCompetitors || "No competitor information provided.",
    );

  const processor = String(stepConfig.processor || "ultra");
  const maxPollAttempts = Number(stepConfig.max_poll_attempts || 135);
  const pollIntervalSeconds = Number(stepConfig.poll_interval_seconds || 20);

  const headers: Record<string, string> = {
    "x-api-key": apiKey,
    "Content-Type": "application/json",
  };

  let runId: string;
  try {
    const createResponse = await fetch("https://api.parallel.ai/v1/tasks/runs", {
      method: "POST",
      headers,
      body: JSON.stringify({ input: prompt, processor }),
    });
    if (!createResponse.ok) {
      const errorText = await createResponse.text();
      return {
        run_id: crypto.randomUUID(),
        operation_id: "company.derive.intel_briefing",
        status: "failed",
        output: null,
        provider_attempts: [
          {
            provider: "parallel",
            action: "deep_research_company_intel_briefing",
            status: "failed",
            error: `task_creation_failed: ${createResponse.status}`,
            raw_response: errorText,
          },
        ],
      };
    }
    const createData = (await createResponse.json()) as { run_id: string; status: string };
    runId = createData.run_id;
    logger.info("Parallel company intel briefing task created", {
      runId,
      processor,
      clientCompanyName,
      targetCompanyName,
      targetCompanyDomain,
    });
  } catch (error) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_company_intel_briefing",
          status: "failed",
          error: `task_creation_exception: ${error instanceof Error ? error.message : String(error)}`,
        },
      ],
    };
  }

  let taskStatus = "queued";
  let pollCount = 0;

  while (taskStatus !== "completed" && taskStatus !== "failed" && pollCount < maxPollAttempts) {
    await wait.for({ seconds: pollIntervalSeconds });
    pollCount++;

    try {
      const statusResponse = await fetch(`https://api.parallel.ai/v1/tasks/runs/${runId}`, {
        method: "GET",
        headers: { "x-api-key": apiKey },
      });
      if (!statusResponse.ok) {
        logger.warn("Parallel company intel briefing status check returned non-OK", {
          runId,
          status: statusResponse.status,
          pollCount,
        });
        continue;
      }
      const statusData = (await statusResponse.json()) as { status: string };
      taskStatus = statusData.status;
      logger.info("Parallel company intel briefing poll", { runId, taskStatus, pollCount });
    } catch (error) {
      logger.warn("Parallel company intel briefing status check exception", {
        runId,
        pollCount,
        error: error instanceof Error ? error.message : String(error),
      });
      continue;
    }
  }

  if (taskStatus === "failed") {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_company_intel_briefing",
          status: "failed",
          error: "parallel_task_failed",
          parallel_run_id: runId,
          poll_count: pollCount,
        },
      ],
    };
  }

  if (taskStatus !== "completed") {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_company_intel_briefing",
          status: "failed",
          error: "poll_timeout",
          parallel_run_id: runId,
          poll_count: pollCount,
          max_poll_attempts: maxPollAttempts,
        },
      ],
    };
  }

  try {
    const resultResponse = await fetch(`https://api.parallel.ai/v1/tasks/runs/${runId}/result`, {
      method: "GET",
      headers: { "x-api-key": apiKey },
    });
    if (!resultResponse.ok) {
      const errorText = await resultResponse.text();
      return {
        run_id: crypto.randomUUID(),
        operation_id: "company.derive.intel_briefing",
        status: "failed",
        output: null,
        provider_attempts: [
          {
            provider: "parallel",
            action: "deep_research_company_intel_briefing",
            status: "failed",
            error: `result_fetch_failed: ${resultResponse.status}`,
            raw_response: errorText,
            parallel_run_id: runId,
          },
        ],
      };
    }
    const resultData = (await resultResponse.json()) as Record<string, unknown>;
    logger.info("Parallel company intel briefing completed", {
      runId,
      pollCount,
      clientCompanyName,
      targetCompanyName,
      targetCompanyDomain,
    });

    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "found",
      output: {
        parallel_run_id: runId,
        processor,
        client_company_name: clientCompanyName,
        client_company_description: clientCompanyDescription,
        target_company_name: targetCompanyName,
        target_company_domain: targetCompanyDomain,
        target_company_description: targetCompanyDescription,
        target_company_industry: targetCompanyIndustry,
        target_company_size: targetCompanySize,
        target_company_funding: targetCompanyFunding,
        parallel_raw_response: resultData,
      },
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_company_intel_briefing",
          status: "found",
          parallel_run_id: runId,
          processor,
          poll_count: pollCount,
        },
      ],
    };
  } catch (error) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.intel_briefing",
      status: "failed",
      output: null,
      provider_attempts: [
        {
          provider: "parallel",
          action: "deep_research_company_intel_briefing",
          status: "failed",
          error: `result_fetch_exception: ${error instanceof Error ? error.message : String(error)}`,
          parallel_run_id: runId,
        },
      ],
    };
  }
}

function getExecutionStartPosition(run: InternalPipelineRun): number {
  const fanOutStart = run.blueprint_snapshot.fan_out?.start_from_position;
  if (typeof fanOutStart === "number" && Number.isInteger(fanOutStart) && fanOutStart > 0) {
    return fanOutStart;
  }

  if (run.step_results.length > 0) {
    return run.step_results.reduce((min, stepResult) => Math.min(min, stepResult.step_position), Number.MAX_SAFE_INTEGER);
  }

  return 1;
}

function resolveInternalConfig(payload: RunPipelinePayload): InternalConfig {
  const apiUrl = payload.api_url || process.env.DATA_ENGINE_API_URL;
  const internalApiKey = payload.internal_api_key || process.env.DATA_ENGINE_INTERNAL_API_KEY;
  if (!apiUrl) throw new Error("DATA_ENGINE_API_URL is not configured");
  if (!internalApiKey) throw new Error("DATA_ENGINE_INTERNAL_API_KEY is not configured");
  return { apiUrl, internalApiKey };
}

async function internalPost<TResponse>(
  internalConfig: InternalConfig,
  path: string,
  payload: Record<string, unknown>,
): Promise<TResponse> {
  const response = await fetch(`${internalConfig.apiUrl}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${internalConfig.internalApiKey}`,
    },
    body: JSON.stringify(payload),
  });
  const body = (await response.json()) as InternalEnvelope<TResponse>;
  if (!response.ok) throw new Error(body.error || `Internal API failed: ${path}`);
  if (body.data === undefined) throw new Error(`Internal API missing data envelope: ${path}`);
  return body.data;
}

async function callExecuteV1(
  internalConfig: InternalConfig,
  params: {
    orgId: string;
    companyId: string;
    operationId: string;
    entityType: "person" | "company" | "job";
    input: Record<string, unknown>;
    options: Record<string, unknown> | null;
  },
): Promise<NonNullable<ExecuteResponseEnvelope["data"]>> {
  const { orgId, companyId, operationId, entityType, input, options } = params;
  const response = await fetch(`${internalConfig.apiUrl}/api/v1/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${internalConfig.internalApiKey}`,
      "x-internal-org-id": orgId,
      "x-internal-company-id": companyId,
    },
    body: JSON.stringify({
      operation_id: operationId,
      entity_type: entityType,
      input,
      options: options ?? undefined,
    }),
  });
  const body = (await response.json()) as ExecuteResponseEnvelope;
  if (!response.ok) throw new Error(body.error || `Execute v1 request failed (${response.status})`);
  if (!body.data) throw new Error("Execute v1 response missing data envelope");
  return body.data as NonNullable<ExecuteResponseEnvelope["data"]>;
}

async function callEntityStateFreshnessCheck(
  internalConfig: InternalConfig,
  params: {
    orgId: string;
    companyId: string;
    entityType: "person" | "company" | "job";
    identifiers: Record<string, unknown>;
    maxAgeHours: number;
  },
): Promise<FreshnessCheckResponse> {
  const response = await fetch(`${internalConfig.apiUrl}/api/internal/entity-state/check-freshness`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${internalConfig.internalApiKey}`,
      "x-internal-org-id": params.orgId,
      "x-internal-company-id": params.companyId,
    },
    body: JSON.stringify({
      entity_type: params.entityType,
      identifiers: params.identifiers,
      max_age_hours: params.maxAgeHours,
    }),
  });
  const body = (await response.json()) as InternalEnvelope<FreshnessCheckResponse>;
  if (!response.ok) throw new Error(body.error || "Freshness check request failed");
  if (!body.data) throw new Error("Freshness check response missing data envelope");
  return body.data;
}

function entityTypeFromOperationId(operationId: string): "person" | "company" | "job" {
  if (operationId.startsWith("person.")) return "person";
  if (operationId.startsWith("job.")) return "job";
  return "company";
}

function mergeContext(
  current: Record<string, unknown>,
  output: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  if (!output) return current;
  return { ...current, ...output };
}

function extractFanOutResults(output: Record<string, unknown> | null | undefined): Array<Record<string, unknown>> {
  if (!output) return [];
  const value = output["results"];
  if (!Array.isArray(value)) return [];
  return value.filter((item) => typeof item === "object" && item !== null) as Array<Record<string, unknown>>;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getStepCondition(
  stepSnapshot: InternalPipelineRun["blueprint_snapshot"]["steps"][number],
): Record<string, unknown> | null {
  if (isObject(stepSnapshot.step_config) && "condition" in stepSnapshot.step_config) {
    const fromConfig = stepSnapshot.step_config.condition;
    if (isObject(fromConfig)) return fromConfig;
    if (fromConfig === null) return null;
  }
  if (isObject(stepSnapshot.condition)) {
    return stepSnapshot.condition;
  }
  return null;
}

function getSkipIfFreshConfig(
  stepSnapshot: InternalPipelineRun["blueprint_snapshot"]["steps"][number],
): SkipIfFreshConfig | null {
  const rawConfig = isObject(stepSnapshot.step_config) ? stepSnapshot.step_config.skip_if_fresh : null;
  if (!isObject(rawConfig)) return null;

  const maxAgeRaw = rawConfig.max_age_hours;
  const identityFieldsRaw = rawConfig.identity_fields;

  if (typeof maxAgeRaw !== "number" || !Number.isFinite(maxAgeRaw) || maxAgeRaw <= 0) return null;
  if (!Array.isArray(identityFieldsRaw)) return null;

  const identityFields = identityFieldsRaw
    .filter((field): field is string => typeof field === "string")
    .map((field) => field.trim())
    .filter((field) => field.length > 0);

  if (identityFields.length === 0) return null;
  return { maxAgeHours: maxAgeRaw, identityFields };
}

function extractFreshnessIdentifiers(
  cumulativeContext: Record<string, unknown>,
  identityFields: string[],
): Record<string, unknown> {
  return identityFields.reduce<Record<string, unknown>>((acc, field) => {
    const value = cumulativeContext[field];
    if (value !== undefined && value !== null && value !== "") {
      acc[field] = value;
    }
    return acc;
  }, {});
}

function inferFieldsUpdatedFromOperationResult(
  operationResult: Record<string, unknown> | null | undefined,
): string[] | null {
  if (!isObject(operationResult) || !isObject(operationResult.output)) {
    return null;
  }
  const keys = Object.entries(operationResult.output)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key]) => key)
    .sort();
  return keys.length > 0 ? keys : null;
}

function operationIdForStep(
  step: InternalPipelineRun["blueprint_snapshot"]["steps"][number] | undefined,
): string {
  return step?.operation_id || "unknown.operation";
}

async function emitStepTimelineEvent(
  internalConfig: InternalConfig,
  payload: {
    orgId: string;
    companyId: string;
    submissionId: string;
    pipelineRunId: string;
    entityType: "person" | "company" | "job";
    cumulativeContext: Record<string, unknown>;
    stepResultId: string;
    stepPosition: number;
    operationId: string;
    stepStatus: "succeeded" | "failed" | "skipped";
    skipReason?: string | null;
    durationMs?: number | null;
    providerAttempts?: Array<Record<string, unknown>>;
    condition?: Record<string, unknown> | null;
    errorMessage?: string | null;
    errorDetails?: Record<string, unknown> | null;
    operationResult?: Record<string, unknown> | null;
  },
): Promise<void> {
  try {
    await internalPost(internalConfig, "/api/internal/entity-timeline/record-step-event", {
      org_id: payload.orgId,
      company_id: payload.companyId,
      submission_id: payload.submissionId,
      pipeline_run_id: payload.pipelineRunId,
      entity_type: payload.entityType,
      cumulative_context: payload.cumulativeContext,
      step_result_id: payload.stepResultId,
      step_position: payload.stepPosition,
      operation_id: payload.operationId,
      step_status: payload.stepStatus,
      skip_reason: payload.skipReason ?? null,
      duration_ms: payload.durationMs ?? null,
      provider_attempts: payload.providerAttempts ?? [],
      condition: payload.condition ?? null,
      error_message: payload.errorMessage ?? null,
      error_details: payload.errorDetails ?? null,
      operation_result: payload.operationResult ?? null,
      fields_updated: inferFieldsUpdatedFromOperationResult(payload.operationResult),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    logger.warn("step timeline emit failed", {
      pipeline_run_id: payload.pipelineRunId,
      step_result_id: payload.stepResultId,
      step_position: payload.stepPosition,
      operation_id: payload.operationId,
      step_status: payload.stepStatus,
      error: message,
    });
  }
}

async function skipStepWithReason(
  internalConfig: InternalConfig,
  stepResultId: string,
  cumulativeContext: Record<string, unknown>,
  skipReason: string,
  metadata: Record<string, unknown>,
): Promise<InternalStepResult> {
  return internalPost<InternalStepResult>(internalConfig, "/api/internal/step-results/update", {
    step_result_id: stepResultId,
    status: "skipped",
    input_payload: cumulativeContext,
    output_payload: {
      skip_reason: skipReason,
      metadata,
    },
  });
}

export const runPipeline = task({
  id: "run-pipeline",
  retry: { maxAttempts: 1 },
  run: async (payload: RunPipelinePayload) => {
    const { pipeline_run_id, org_id, company_id } = payload;
    const internalConfig = resolveInternalConfig(payload);
    logger.info("run-pipeline start", { pipeline_run_id, org_id, company_id });

    const run = await internalPost<InternalPipelineRun>(
      internalConfig,
      "/api/internal/pipeline-runs/get",
      { pipeline_run_id },
    );

    await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
      pipeline_run_id,
      status: "running",
    });
    await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
      submission_id: run.submission_id,
    });

    const executionStartPosition = getExecutionStartPosition(run);
    const orderedSteps = [...run.blueprint_snapshot.steps]
      .filter((step) => step.is_enabled !== false)
      .filter((step) => step.position >= executionStartPosition)
      .sort((a, b) => a.position - b.position);
    const stepsByPosition = new Map(orderedSteps.map((step) => [step.position, step]));

    const snapshotEntity = run.blueprint_snapshot.entity || {};
    const entityType =
      snapshotEntity.entity_type === "person" ||
      snapshotEntity.entity_type === "company" ||
      snapshotEntity.entity_type === "job"
        ? snapshotEntity.entity_type
        : "company";
    const submissionInput =
      run.submissions.input_payload &&
      typeof run.submissions.input_payload === "object" &&
      !Array.isArray(run.submissions.input_payload)
        ? (run.submissions.input_payload as Record<string, unknown>)
        : {};
    const initialInput = snapshotEntity.input || submissionInput;
    let cumulativeContext: Record<string, unknown> = { ...initialInput };
    let lastSuccessfulOperationId: string | null = null;
    let shouldShortCircuitRemainingSteps = false;

    for (const stepSnapshot of orderedSteps) {
      if (shouldShortCircuitRemainingSteps) {
        break;
      }

      const stepResult = run.step_results.find((sr) => sr.step_position === stepSnapshot.position);
      if (!stepResult) throw new Error(`Missing step_result for position ${stepSnapshot.position}`);

      const operationId = stepSnapshot.operation_id;
      if (!operationId) {
        const message = `Missing operation_id for blueprint step at position ${stepSnapshot.position}`;
        const failedStep = await internalPost<InternalStepResult>(
          internalConfig,
          "/api/internal/step-results/update",
          {
            step_result_id: stepResult.id,
            status: "failed",
            input_payload: cumulativeContext,
            error_message: message,
            error_details: { error: message },
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType,
          cumulativeContext,
          stepResultId: failedStep.id,
          stepPosition: failedStep.step_position,
          operationId: "unknown.operation",
          stepStatus: "failed",
          durationMs: failedStep.duration_ms,
          errorMessage: message,
          errorDetails: { error: message },
        });
        const skippedRows = await internalPost<Array<InternalStepResult>>(
          internalConfig,
          "/api/internal/step-results/mark-remaining-skipped",
          {
            pipeline_run_id,
            from_step_position: stepSnapshot.position,
          },
        );
        for (const skippedStep of skippedRows) {
          const skippedBlueprintStep = stepsByPosition.get(skippedStep.step_position);
          await emitStepTimelineEvent(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            submissionId: run.submission_id,
            pipelineRunId: pipeline_run_id,
            entityType: entityTypeFromOperationId(operationIdForStep(skippedBlueprintStep)),
            cumulativeContext,
            stepResultId: skippedStep.id,
            stepPosition: skippedStep.step_position,
            operationId: operationIdForStep(skippedBlueprintStep),
            stepStatus: "skipped",
            skipReason: "upstream_step_failed",
            durationMs: skippedStep.duration_ms,
            errorMessage: "Skipped because a prior step failed",
            errorDetails: {
              failed_step_position: stepSnapshot.position,
            },
          });
        }
        await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
          pipeline_run_id,
          status: "failed",
          error_message: message,
          error_details: { error: message },
        });
        await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
          submission_id: run.submission_id,
        });
        return { pipeline_run_id, status: "failed", failed_step_position: stepSnapshot.position, error: message };
      }

      const condition = getStepCondition(stepSnapshot);
      const shouldRun = evaluateCondition(condition, cumulativeContext);
      if (!shouldRun) {
        const skippedStep = await skipStepWithReason(
          internalConfig,
          stepResult.id,
          cumulativeContext,
          "condition_not_met",
          {
            condition,
            step_position: stepSnapshot.position,
            operation_id: operationId,
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType: entityTypeFromOperationId(operationId),
          cumulativeContext,
          stepResultId: skippedStep.id,
          stepPosition: skippedStep.step_position,
          operationId,
          stepStatus: "skipped",
          skipReason: "condition_not_met",
          durationMs: skippedStep.duration_ms,
          condition,
        });

        const fanOutEnabled =
          stepSnapshot.fan_out === true ||
          stepSnapshot.step_config?.fan_out === true;

        if (fanOutEnabled) {
          for (const downstreamStep of orderedSteps) {
            if (downstreamStep.position <= stepSnapshot.position) continue;
            const downstreamStepResult = run.step_results.find(
              (sr) => sr.step_position === downstreamStep.position,
            );
            if (!downstreamStepResult) continue;
            const downstreamSkippedStep = await skipStepWithReason(
              internalConfig,
              downstreamStepResult.id,
              cumulativeContext,
              "parent_step_condition_not_met",
              {
                parent_step_position: stepSnapshot.position,
                parent_operation_id: operationId,
                parent_condition: condition,
              },
            );
            await emitStepTimelineEvent(internalConfig, {
              orgId: org_id,
              companyId: company_id,
              submissionId: run.submission_id,
              pipelineRunId: pipeline_run_id,
              entityType: entityTypeFromOperationId(operationIdForStep(downstreamStep)),
              cumulativeContext,
              stepResultId: downstreamSkippedStep.id,
              stepPosition: downstreamSkippedStep.step_position,
              operationId: operationIdForStep(downstreamStep),
              stepStatus: "skipped",
              skipReason: "parent_step_condition_not_met",
              durationMs: downstreamSkippedStep.duration_ms,
              condition,
              errorDetails: {
                parent_step_position: stepSnapshot.position,
                parent_operation_id: operationId,
              },
            });
          }
          shouldShortCircuitRemainingSteps = true;
        }

        continue;
      }

      const stepEntityType = entityTypeFromOperationId(operationId);
      const skipIfFresh = getSkipIfFreshConfig(stepSnapshot);
      if (skipIfFresh) {
        try {
          const freshness = await callEntityStateFreshnessCheck(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            entityType: stepEntityType,
            identifiers: extractFreshnessIdentifiers(cumulativeContext, skipIfFresh.identityFields),
            maxAgeHours: skipIfFresh.maxAgeHours,
          });

          if (freshness.fresh) {
            cumulativeContext = mergeContext(cumulativeContext, freshness.canonical_payload);
            const freshnessMetadata = {
              entity_id: freshness.entity_id ?? null,
              age_hours: freshness.age_hours ?? null,
              last_enriched_at: freshness.last_enriched_at ?? null,
              max_age_hours: skipIfFresh.maxAgeHours,
              identity_fields: skipIfFresh.identityFields,
            };
            const skippedStep = await skipStepWithReason(
              internalConfig,
              stepResult.id,
              cumulativeContext,
              "entity_state_fresh",
              freshnessMetadata,
            );
            await emitStepTimelineEvent(internalConfig, {
              orgId: org_id,
              companyId: company_id,
              submissionId: run.submission_id,
              pipelineRunId: pipeline_run_id,
              entityType: stepEntityType,
              cumulativeContext,
              stepResultId: skippedStep.id,
              stepPosition: skippedStep.step_position,
              operationId,
              stepStatus: "skipped",
              skipReason: "entity_state_fresh",
              durationMs: skippedStep.duration_ms,
              condition,
              errorDetails: freshnessMetadata,
            });
            continue;
          }
        } catch (error) {
          logger.warn("freshness check failed; continuing with live execution", {
            pipeline_run_id,
            step_position: stepSnapshot.position,
            operation_id: operationId,
            error: error instanceof Error ? error.message : String(error),
          });
        }
      }

      await internalPost(internalConfig, "/api/internal/step-results/update", {
        step_result_id: stepResult.id,
        status: "running",
        input_payload: cumulativeContext,
      });

      try {
        let result: NonNullable<ExecuteResponseEnvelope["data"]>;
        if (operationId === "company.derive.icp_job_titles") {
          result = await executeParallelDeepResearch(cumulativeContext, stepSnapshot.step_config || {});
        } else if (operationId === "company.derive.intel_briefing") {
          result = await executeCompanyIntelBriefing(cumulativeContext, stepSnapshot.step_config || {});
        } else {
          result = await callExecuteV1(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            operationId,
            entityType: stepEntityType,
            input: cumulativeContext,
            options: stepSnapshot.step_config || null,
          });
        }

        cumulativeContext = mergeContext(cumulativeContext, result.output);
        const stepFailed = result.status === "failed";
        if (stepFailed) {
          const message = `Operation failed: ${operationId}`;
          const failedStep = await internalPost<InternalStepResult>(
            internalConfig,
            "/api/internal/step-results/update",
            {
              step_result_id: stepResult.id,
              status: "failed",
              output_payload: {
                operation_result: result,
                cumulative_context: cumulativeContext,
              },
              error_message: message,
              error_details: {
                operation_id: operationId,
                missing_inputs: result.missing_inputs || [],
              },
            },
          );
          await emitStepTimelineEvent(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            submissionId: run.submission_id,
            pipelineRunId: pipeline_run_id,
            entityType: stepEntityType,
            cumulativeContext,
            stepResultId: failedStep.id,
            stepPosition: failedStep.step_position,
            operationId,
            stepStatus: "failed",
            durationMs: failedStep.duration_ms,
            providerAttempts: Array.isArray(result.provider_attempts) ? result.provider_attempts : [],
            errorMessage: message,
            errorDetails: {
              operation_id: operationId,
              missing_inputs: result.missing_inputs || [],
            },
            operationResult: result as unknown as Record<string, unknown>,
          });
          const skippedRows = await internalPost<Array<InternalStepResult>>(
            internalConfig,
            "/api/internal/step-results/mark-remaining-skipped",
            {
              pipeline_run_id,
              from_step_position: stepSnapshot.position,
            },
          );
          for (const skippedStep of skippedRows) {
            const skippedBlueprintStep = stepsByPosition.get(skippedStep.step_position);
            await emitStepTimelineEvent(internalConfig, {
              orgId: org_id,
              companyId: company_id,
              submissionId: run.submission_id,
              pipelineRunId: pipeline_run_id,
              entityType: entityTypeFromOperationId(operationIdForStep(skippedBlueprintStep)),
              cumulativeContext,
              stepResultId: skippedStep.id,
              stepPosition: skippedStep.step_position,
              operationId: operationIdForStep(skippedBlueprintStep),
              stepStatus: "skipped",
              skipReason: "upstream_step_failed",
              durationMs: skippedStep.duration_ms,
              errorMessage: "Skipped because a prior step failed",
              errorDetails: {
                failed_step_position: stepSnapshot.position,
                failed_operation_id: operationId,
              },
            });
          }
          await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
            pipeline_run_id,
            status: "failed",
            error_message: message,
            error_details: { operation_id: operationId, missing_inputs: result.missing_inputs || [] },
          });
          await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
            submission_id: run.submission_id,
          });
          return { pipeline_run_id, status: "failed", failed_step_position: stepSnapshot.position, error: message };
        }

        const succeededStep = await internalPost<InternalStepResult>(
          internalConfig,
          "/api/internal/step-results/update",
          {
            step_result_id: stepResult.id,
            status: "succeeded",
            output_payload: {
              operation_result: result,
              cumulative_context: cumulativeContext,
            },
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType: stepEntityType,
          cumulativeContext,
          stepResultId: succeededStep.id,
          stepPosition: succeededStep.step_position,
          operationId,
          stepStatus: "succeeded",
          durationMs: succeededStep.duration_ms,
          providerAttempts: Array.isArray(result.provider_attempts) ? result.provider_attempts : [],
          operationResult: result as unknown as Record<string, unknown>,
        });
        lastSuccessfulOperationId = operationId;

        const fanOutEnabled =
          stepSnapshot.fan_out === true ||
          stepSnapshot.step_config?.fan_out === true;
        if (fanOutEnabled) {
          const fanOutEntities = extractFanOutResults(result.output);
          const providerAttempts = Array.isArray(result.provider_attempts)
            ? result.provider_attempts
            : [];
          const fanOutProvider = providerAttempts.find(
            (attempt) => attempt?.status === "found" || attempt?.status === "succeeded",
          )?.provider as string | undefined;

          const fanOutResponse = await internalPost<FanOutChildRunsResponse>(
            internalConfig,
            "/api/internal/pipeline-runs/fan-out",
            {
              parent_pipeline_run_id: pipeline_run_id,
              submission_id: run.submission_id,
              org_id,
              company_id,
              blueprint_snapshot: run.blueprint_snapshot,
              fan_out_entities: fanOutEntities,
              start_from_position: stepSnapshot.position + 1,
              parent_cumulative_context: cumulativeContext,
              fan_out_operation_id: operationId,
              provider: fanOutProvider ?? null,
              provider_attempts: providerAttempts,
            },
          );

          await internalPost(internalConfig, "/api/internal/step-results/update", {
            step_result_id: stepResult.id,
            status: "succeeded",
            output_payload: {
              operation_result: result,
              cumulative_context: cumulativeContext,
              fan_out: {
                child_run_ids: fanOutResponse.child_run_ids,
                child_count: fanOutResponse.child_run_ids.length,
                child_count_created: fanOutResponse.child_run_ids.length,
                child_count_skipped_duplicates: fanOutResponse.skipped_duplicates_count ?? 0,
                skipped_duplicate_identifiers: fanOutResponse.skipped_duplicate_identifiers ?? [],
                start_from_position: stepSnapshot.position + 1,
              },
            },
          });

          await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
            pipeline_run_id,
            status: "succeeded",
            error_message: null,
            error_details: null,
          });
          try {
            await internalPost(internalConfig, "/api/internal/entity-state/upsert", {
              pipeline_run_id,
              entity_type: entityType,
              cumulative_context: cumulativeContext,
              last_operation_id: lastSuccessfulOperationId,
            });
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
              pipeline_run_id,
              status: "failed",
              error_message: "Entity state upsert failed",
              error_details: { error: message },
            });
            await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
              submission_id: run.submission_id,
            });
            return { pipeline_run_id, status: "failed", error: message };
          }
          await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
            submission_id: run.submission_id,
          });
          return {
            pipeline_run_id,
            status: "succeeded",
            fan_out_child_run_ids: fanOutResponse.child_run_ids,
            fan_out_child_count: fanOutResponse.child_run_ids.length,
          };
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const failedStep = await internalPost<InternalStepResult>(
          internalConfig,
          "/api/internal/step-results/update",
          {
            step_result_id: stepResult.id,
            status: "failed",
            error_message: message,
            error_details: { error: message },
          },
        );
        await emitStepTimelineEvent(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          submissionId: run.submission_id,
          pipelineRunId: pipeline_run_id,
          entityType: entityTypeFromOperationId(operationId),
          cumulativeContext,
          stepResultId: failedStep.id,
          stepPosition: failedStep.step_position,
          operationId,
          stepStatus: "failed",
          durationMs: failedStep.duration_ms,
          errorMessage: message,
          errorDetails: { error: message },
        });
        const skippedRows = await internalPost<Array<InternalStepResult>>(
          internalConfig,
          "/api/internal/step-results/mark-remaining-skipped",
          {
            pipeline_run_id,
            from_step_position: stepSnapshot.position,
          },
        );
        for (const skippedStep of skippedRows) {
          const skippedBlueprintStep = stepsByPosition.get(skippedStep.step_position);
          await emitStepTimelineEvent(internalConfig, {
            orgId: org_id,
            companyId: company_id,
            submissionId: run.submission_id,
            pipelineRunId: pipeline_run_id,
            entityType: entityTypeFromOperationId(operationIdForStep(skippedBlueprintStep)),
            cumulativeContext,
            stepResultId: skippedStep.id,
            stepPosition: skippedStep.step_position,
            operationId: operationIdForStep(skippedBlueprintStep),
            stepStatus: "skipped",
            skipReason: "upstream_step_failed",
            durationMs: skippedStep.duration_ms,
            errorMessage: "Skipped because a prior step failed",
            errorDetails: {
              failed_step_position: stepSnapshot.position,
              failed_operation_id: operationId,
            },
          });
        }
        await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
          pipeline_run_id,
          status: "failed",
          error_message: message,
          error_details: { error: message },
        });
        await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
          submission_id: run.submission_id,
        });
        return { pipeline_run_id, status: "failed", failed_step_position: stepSnapshot.position, error: message };
      }
    }

    await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
      pipeline_run_id,
      status: "succeeded",
      error_message: null,
      error_details: null,
    });
    try {
      await internalPost(internalConfig, "/api/internal/entity-state/upsert", {
        pipeline_run_id,
        entity_type: entityType,
        cumulative_context: cumulativeContext,
        last_operation_id: lastSuccessfulOperationId,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      await internalPost(internalConfig, "/api/internal/pipeline-runs/update-status", {
        pipeline_run_id,
        status: "failed",
        error_message: "Entity state upsert failed",
        error_details: { error: message },
      });
      await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
        submission_id: run.submission_id,
      });
      return { pipeline_run_id, status: "failed", error: message };
    }
    await internalPost(internalConfig, "/api/internal/submissions/sync-status", {
      submission_id: run.submission_id,
    });
    return { pipeline_run_id, status: "succeeded" };
  },
});

export const __testables = {
  extractFreshnessIdentifiers,
  getSkipIfFreshConfig,
  inferFieldsUpdatedFromOperationResult,
  operationIdForStep,
};
