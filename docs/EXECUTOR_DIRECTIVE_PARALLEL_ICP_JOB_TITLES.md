# Directive: `company.derive.icp_job_titles` — Parallel Deep Research in Trigger.dev

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We are adding a new enrichment operation that uses Parallel.ai's Deep Research API to discover ICP (Ideal Customer Profile) job titles for a given company. Unlike all other operations in the system, this one is long-running (5–25 minutes) and cannot route through FastAPI/Railway due to Railway's 15-minute HTTP timeout. Instead, Trigger.dev calls Parallel.ai directly from the pipeline runner, polls for completion, and stores the raw result. The prompt has been validated in the Parallel.ai UI and produces high-quality structured output. No output mapping or extraction is needed — we store the raw Parallel.ai response as-is.

---

## Parallel.ai Deep Research API Reference

**Auth:** `x-api-key` header. The key is available as `process.env.PARALLEL_API_KEY` in Trigger.dev runtime.

### Create Task

```
POST https://api.parallel.ai/v1/tasks/runs
Headers: x-api-key, Content-Type: application/json
Body: { "input": "<prompt string>", "processor": "pro" }
Response: { "run_id": "trun_...", "status": "queued", "processor": "pro" }
```

Returns immediately. The task runs asynchronously.

### Check Task Status

```
GET https://api.parallel.ai/v1/tasks/runs/{run_id}
Headers: x-api-key
Response: { "run_id": "trun_...", "status": "queued" | "running" | "completed" | "failed", ... }
```

### Fetch Task Result

```
GET https://api.parallel.ai/v1/tasks/runs/{run_id}/result
Headers: x-api-key
Response: {
  "run": { "run_id": "trun_...", "status": "completed", "processor": "pro", ... },
  "output": { "basis": [...], "type": "json", "content": { ... } }
}
```

This endpoint blocks until the task is complete. However, we use polling instead so we can leverage `wait.for()` for zero-cost pausing.

---

## Existing code to read before starting

- `trigger/src/tasks/run-pipeline.ts` — the entire file. This is the only file you will modify. Pay close attention to:
  - Line 1: current imports
  - Lines 63–73: `ExecuteResponseEnvelope` interface (the result shape you must return)
  - Lines 144–175: `callExecuteV1` function (the standard execution path you are adding an alternative to)
  - Lines 632–646: the step execution try block where `callExecuteV1` is called (this is where your branch goes)
  - Lines 648–757: how results are handled after execution (context merge, failure handling, success handling) — your result must be compatible with this code
- `docs/api-reference-docs/parallel/icp-job-titles-curl.md` — the validated CURL with the exact prompt that works

---

## Deliverable 1: Parallel Deep Research Execution in `run-pipeline.ts`

**File:** `trigger/src/tasks/run-pipeline.ts`

### 1a. Add `wait` import

Change line 1 from:

```typescript
import { logger, task } from "@trigger.dev/sdk/v3";
```

to:

```typescript
import { logger, task, wait } from "@trigger.dev/sdk/v3";
```

If `wait` is not exported from `@trigger.dev/sdk/v3`, try:

```typescript
import { logger, task } from "@trigger.dev/sdk/v3";
import { wait } from "@trigger.dev/sdk";
```

Verify which import works by checking the SDK types. Do not guess — one of these two will work with SDK version 4.4.0.

### 1b. Add the prompt template constant

Place this after the existing interface definitions (after line ~120, before the `internalPost` function). This is the exact prompt from the validated CURL with placeholders for company data:

```typescript
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
   - **Champions** — Day-to-day users or people experiencing the problem directly. They discover, evaluate, and advocate internally.
   - **Evaluators** — Technical or operational stakeholders who run POCs or compare alternatives.
   - **Decision makers** — Budget owners and signers. Only include if appropriate for this product category and price point.

3. Generate title variations
   For each persona:
   - Include realistic seniority variants (Manager, Senior Manager, Director, Head, VP, Lead) only where appropriate.
   - Include function-specific variants where relevant (e.g., Security, Compliance, GRC, IT, Engineering, Legal, Risk).

CRITICAL GUARDRAILS
- Every title must be grounded in evidence from the company website, reviews, case studies, or known buyer patterns for this category.
- Do not guess or hallucinate titles.
- Exclude roles that would reasonably not care about or buy this product.
- Do not include generic functional labels (e.g., "Information Security").
- Quantity target: 30–60 titles. More is fine if grounded. Fewer is fine if narrow. Never pad.

OUTPUT FORMAT
companyName: {company_name}
domain: {domain}
inferredProduct: One sentence describing what the company sells and to whom, based on your research.
buyerPersonaSummary: 2–3 sentences describing the buying committee — who champions it, who evaluates it, who signs off.
titles: For each title include the title, buyerRole (champion | evaluator | decision_maker), and reasoning (one sentence grounding this title in research evidence).`;
```

### 1c. Add the `executeParallelDeepResearch` function

Place this after the prompt template constant, before the `runPipeline` task definition.

```typescript
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
      provider_attempts: [{
        provider: "parallel",
        action: "deep_research_icp_job_titles",
        status: "skipped",
        skip_reason: "missing_parallel_api_key",
      }],
    };
  }

  const companyName = String(cumulativeContext.company_name || cumulativeContext.companyName || "");
  const domain = String(cumulativeContext.domain || cumulativeContext.company_domain || "");
  const companyDescription = String(cumulativeContext.company_description || cumulativeContext.description || "");

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

  const prompt = ICP_JOB_TITLES_PROMPT_TEMPLATE
    .replaceAll("{company_name}", companyName)
    .replaceAll("{domain}", domain)
    .replaceAll("{company_description}", companyDescription || "No description provided.");

  const processor = String(stepConfig.processor || "pro");
  const maxPollAttempts = Number(stepConfig.max_poll_attempts || 90);
  const pollIntervalSeconds = Number(stepConfig.poll_interval_seconds || 20);

  const headers: Record<string, string> = {
    "x-api-key": apiKey,
    "Content-Type": "application/json",
  };

  // --- Step 1: Create the task ---
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
        provider_attempts: [{
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "failed",
          error: `task_creation_failed: ${createResponse.status}`,
          raw_response: errorText,
        }],
      };
    }
    const createData = await createResponse.json() as { run_id: string; status: string };
    runId = createData.run_id;
    logger.info("Parallel deep research task created", { runId, processor, companyName, domain });
  } catch (error) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [{
        provider: "parallel",
        action: "deep_research_icp_job_titles",
        status: "failed",
        error: `task_creation_exception: ${error instanceof Error ? error.message : String(error)}`,
      }],
    };
  }

  // --- Step 2: Poll for completion ---
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
        logger.warn("Parallel status check returned non-OK", { runId, status: statusResponse.status, pollCount });
        continue;
      }
      const statusData = await statusResponse.json() as { status: string };
      taskStatus = statusData.status;
      logger.info("Parallel deep research poll", { runId, taskStatus, pollCount });
    } catch (error) {
      logger.warn("Parallel status check exception", { runId, pollCount, error: error instanceof Error ? error.message : String(error) });
      continue;
    }
  }

  if (taskStatus === "failed") {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [{
        provider: "parallel",
        action: "deep_research_icp_job_titles",
        status: "failed",
        error: "parallel_task_failed",
        parallel_run_id: runId,
        poll_count: pollCount,
      }],
    };
  }

  if (taskStatus !== "completed") {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [{
        provider: "parallel",
        action: "deep_research_icp_job_titles",
        status: "failed",
        error: "poll_timeout",
        parallel_run_id: runId,
        poll_count: pollCount,
        max_poll_attempts: maxPollAttempts,
      }],
    };
  }

  // --- Step 3: Fetch the result ---
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
        provider_attempts: [{
          provider: "parallel",
          action: "deep_research_icp_job_titles",
          status: "failed",
          error: `result_fetch_failed: ${resultResponse.status}`,
          raw_response: errorText,
          parallel_run_id: runId,
        }],
      };
    }
    const resultData = await resultResponse.json() as Record<string, unknown>;
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
      provider_attempts: [{
        provider: "parallel",
        action: "deep_research_icp_job_titles",
        status: "found",
        parallel_run_id: runId,
        processor,
        poll_count: pollCount,
      }],
    };
  } catch (error) {
    return {
      run_id: crypto.randomUUID(),
      operation_id: "company.derive.icp_job_titles",
      status: "failed",
      output: null,
      provider_attempts: [{
        provider: "parallel",
        action: "deep_research_icp_job_titles",
        status: "failed",
        error: `result_fetch_exception: ${error instanceof Error ? error.message : String(error)}`,
        parallel_run_id: runId,
      }],
    };
  }
}
```

### 1d. Add the step execution branch

In the step execution loop, change lines 638–646 from:

```typescript
      try {
        const result = await callExecuteV1(internalConfig, {
          orgId: org_id,
          companyId: company_id,
          operationId,
          entityType: stepEntityType,
          input: cumulativeContext,
          options: stepSnapshot.step_config || null,
        });
```

to:

```typescript
      try {
        let result: NonNullable<ExecuteResponseEnvelope["data"]>;
        if (operationId === "company.derive.icp_job_titles") {
          result = await executeParallelDeepResearch(
            cumulativeContext,
            stepSnapshot.step_config || {},
          );
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
```

Everything after this point (lines 648–757+) remains completely unchanged. The result has the same shape regardless of which path produced it.

Commit with message: `add Parallel Deep Research execution for company.derive.icp_job_titles in pipeline runner`

---

## Deliverable 2: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to the Company Derive section:

```
| `company.derive.icp_job_titles` | Parallel.ai Deep Research (direct from Trigger.dev — long-running async) |
```

Update operation count accordingly.

### File: `CLAUDE.md`

In the Environment Configuration section, add:

```
- `PARALLEL_API_KEY` — API key for Parallel.ai Deep Research (set in Trigger.dev env vars, NOT in Doppler/Railway — this operation runs directly from Trigger.dev).
```

Commit with message: `update docs for company.derive.icp_job_titles operation`

---

## What is NOT in scope

- No FastAPI changes (no provider adapter, no contract, no router wiring, no operation service)
- No output mapping or extraction — raw Parallel.ai response is stored as-is
- No `task_spec.output_schema` — the prompt produces structured output via the default `auto` schema
- No generic async step abstraction — this is scoped to `company.derive.icp_job_titles` only
- No HQ fetch step (that is built separately)
- No blueprint creation (separate task)
- No deploy commands
- No database migrations

## Prerequisites (already done, do not redo)

- `PARALLEL_API_KEY` is already set in Trigger.dev env vars
- The HQ endpoint for fetching company data exists at `POST https://api.revenueinfra.com/api/admin/temp/companies-for-parallel-icp`

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Which `wait` import path worked (`@trigger.dev/sdk/v3` or `@trigger.dev/sdk`)
(b) The `executeParallelDeepResearch` function signature
(c) The fields extracted from cumulative context for prompt interpolation (list all aliases checked)
(d) The result shape returned on success (field names in `output`)
(e) The step execution branch location (exact line numbers before/after)
(f) Error handling paths (list all failure modes and what status/error they produce)
(g) Anything to flag
