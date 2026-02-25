# Directive: `company.derive.intel_briefing` — Parallel Deep Research Company Intel Briefing

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We already have `company.derive.icp_job_titles` implemented as a Parallel.ai Deep Research operation that runs directly from Trigger.dev's pipeline runner (bypassing FastAPI for the long-running API call). This directive adds a second Deep Research operation following the exact same pattern. This operation produces a structured company intelligence briefing for a target company, framed through the lens of a client company's product. The briefing covers business context, financials, strategic initiatives, operational bottlenecks, posture/gaps, competitor profiles, and strategic relevance to the client. The processor is `ultra` (longer running, higher quality than `pro`).

---

## Parallel.ai Deep Research API Reference

Same API as `company.derive.icp_job_titles`. Auth: `x-api-key` header via `process.env.PARALLEL_API_KEY`.

- `POST https://api.parallel.ai/v1/tasks/runs` — create task, returns `run_id`
- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}` — check status
- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}/result` — fetch result (blocks until complete)

---

## Existing code to read before starting

- `trigger/src/tasks/run-pipeline.ts` — the only file you will modify. **Read the entire file.** Specifically study:
  - Lines ~97–145: `ICP_JOB_TITLES_PROMPT_TEMPLATE` — your new prompt template goes right after this
  - Lines 147–387: `executeParallelDeepResearch` — **this is your reference implementation.** Your new function is structurally identical. Copy its pattern exactly: API key check, input extraction, prompt interpolation, task creation, poll loop with `wait.for()`, status checks, result fetch, error handling, return shape. The only differences are the prompt template, the input fields, the default processor, and the operation ID.
  - Lines 922–935: the step execution branch — you are adding an `else if` for `company.derive.intel_briefing`
  - The `ExecuteResponseEnvelope` interface (lines 63–73) — your function must return this shape
- `docs/api-reference-docs/parallel/company-intel-briefing-template.md` — the full templated prompt with all dynamic variables and the output schema
- `docs/api-reference-docs/parallel/company-intel-briefing-sample-response.json` — a real response from Parallel.ai for this prompt (SecurityPal → CoreWeave), showing expected output quality and structure

---

## Deliverable 1: Company Intel Briefing Execution in `run-pipeline.ts`

**File:** `trigger/src/tasks/run-pipeline.ts`

### 1a. Add the prompt template constant

Place this after the existing `ICP_JOB_TITLES_PROMPT_TEMPLATE` constant. The prompt is taken from `docs/api-reference-docs/parallel/company-intel-briefing-template.md`. Copy the full prompt from the `"input"` value in the Templated CURL section of that file, with placeholders intact.

The constant must be named:

```typescript
const COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE = `...`;
```

The prompt has these placeholders that will be interpolated at runtime:
- `{client_company_name}`
- `{client_company_description}`
- `{target_company_name}`
- `{target_company_domain}`
- `{target_company_description}`
- `{target_company_industry}`
- `{target_company_size}`
- `{target_company_funding}`
- `{target_company_competitors}`

**Copy the prompt exactly from the template file.** Do not alter the research instructions, output schema, or any prompt text. The only thing that should differ from the template file is that the shell escaping (`'\''`) becomes normal apostrophes in the TypeScript template literal.

### 1b. Add the `executeCompanyIntelBriefing` function

Place this after the existing `executeParallelDeepResearch` function. Follow the **exact same pattern** — create task, poll with `wait.for()`, fetch result, return standard result shape. The differences from `executeParallelDeepResearch` are:

1. **Operation ID:** `"company.derive.intel_briefing"`
2. **Prompt template:** `COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE`
3. **Default processor:** `"ultra"` (not `"pro"`)
4. **More input fields extracted from cumulative context:**

```typescript
const clientCompanyName = String(cumulativeContext.client_company_name || "");
const clientCompanyDescription = String(cumulativeContext.client_company_description || "");
const targetCompanyName = String(cumulativeContext.target_company_name || cumulativeContext.company_name || "");
const targetCompanyDomain = String(cumulativeContext.target_company_domain || cumulativeContext.domain || "");
const targetCompanyDescription = String(cumulativeContext.target_company_description || cumulativeContext.company_description || cumulativeContext.description || "");
const targetCompanyIndustry = String(cumulativeContext.target_company_industry || cumulativeContext.industry || "");
const targetCompanySize = String(cumulativeContext.target_company_size || cumulativeContext.employee_count || cumulativeContext.employee_range || "");
const targetCompanyFunding = String(cumulativeContext.target_company_funding || cumulativeContext.funding || "");
const targetCompanyCompetitors = String(cumulativeContext.target_company_competitors || "");
```

5. **Required inputs check:** `clientCompanyName`, `clientCompanyDescription`, `targetCompanyName`, and `targetCompanyDomain` are required. If any are missing, return `status: "failed"` with `missing_inputs`.

6. **Prompt interpolation:**

```typescript
const prompt = COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE
  .replaceAll("{client_company_name}", clientCompanyName)
  .replaceAll("{client_company_description}", clientCompanyDescription)
  .replaceAll("{target_company_name}", targetCompanyName)
  .replaceAll("{target_company_domain}", targetCompanyDomain)
  .replaceAll("{target_company_description}", targetCompanyDescription || "No description provided.")
  .replaceAll("{target_company_industry}", targetCompanyIndustry || "Not specified")
  .replaceAll("{target_company_size}", targetCompanySize || "Not specified")
  .replaceAll("{target_company_funding}", targetCompanyFunding || "Not specified")
  .replaceAll("{target_company_competitors}", targetCompanyCompetitors || "No competitor information provided.");
```

7. **Default poll config:** `max_poll_attempts` defaults to 135 (45 minutes at 20s intervals, since `ultra` runs longer than `pro`).

8. **Success output shape:**

```typescript
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
}
```

9. **Provider attempts action name:** `"deep_research_company_intel_briefing"`

Everything else — task creation, polling loop, error handling paths, logging — follows `executeParallelDeepResearch` exactly. Do not refactor or abstract shared code between the two functions. Keep them independent.

### 1c. Add the step execution branch

In the step execution branch (around line 922), add `company.derive.intel_briefing` as a second condition:

```typescript
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
```

Commit with message: `add Parallel Deep Research company intel briefing (company.derive.intel_briefing) in pipeline runner`

---

## Deliverable 2: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to the Company Derive section:

```
| `company.derive.intel_briefing` | Parallel.ai Deep Research (direct from Trigger.dev — company intelligence briefing framed through client lens) |
```

Update operation count accordingly (59 total).

### File: `CLAUDE.md`

Update the operation count references if present.

Commit with message: `update docs for company.derive.intel_briefing operation`

---

## What is NOT in scope

- No changes to `executeParallelDeepResearch` (the ICP job titles function) — leave it untouched
- No refactoring to share code between the two Parallel functions — keep them independent
- No FastAPI changes (no provider adapter, no contract, no router wiring)
- No output mapping or extraction — raw Parallel.ai response stored as-is
- No blueprint creation
- No deploy commands
- No database migrations

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) The `executeCompanyIntelBriefing` function signature
(b) All cumulative context fields extracted (list every alias checked for each variable)
(c) Required inputs (which fields cause failure if missing)
(d) Default processor and default max_poll_attempts
(e) The result `output` field names on success
(f) The step execution branch location (exact line numbers)
(g) Error handling paths (list all failure modes — should mirror `executeParallelDeepResearch`)
(h) Anything to flag
