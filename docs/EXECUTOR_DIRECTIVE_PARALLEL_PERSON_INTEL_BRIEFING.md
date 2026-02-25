# Directive: `person.derive.intel_briefing` + Canonical Field Fixes

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have two existing Parallel.ai Deep Research operations in `run-pipeline.ts`: `company.derive.icp_job_titles` and `company.derive.intel_briefing`. This directive adds a third: `person.derive.intel_briefing`, which produces person-level intelligence for outreach. It also fixes a canonical field naming issue in the company intel briefing output that prevents entity state resolution from working correctly.

---

## Parallel.ai Deep Research API Reference

Same API as existing operations. Auth: `x-api-key` header via `process.env.PARALLEL_API_KEY`.

- `POST https://api.parallel.ai/v1/tasks/runs` — create task, returns `run_id`
- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}` — check status
- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}/result` — fetch result

---

## Existing code to read before starting

- `trigger/src/tasks/run-pipeline.ts` — the only file you will modify. **Read the entire file.** Study:
  - `executeCompanyIntelBriefing` function (starts around line 485) — **this is your reference implementation.** Your new function is structurally identical. Copy its pattern exactly.
  - The step execution branch (around lines 1307–1322) — you will add another `else if` for `person.derive.intel_briefing`
  - The success output shape at lines 726–753 — your output must follow the same pattern, AND you will fix this output (Deliverable 1)
- `docs/api-reference-docs/parallel/person-intel-briefing-template.md` — the full templated prompt with all dynamic variables and the genericized output schema
- `docs/api-reference-docs/parallel/person-intel-briefing-sample-response.json` — a real response from Parallel.ai (SecurityPal → Jim Higgins @ CoreWeave)

---

## Deliverable 1: Fix Canonical Fields in Company Intel Briefing Output

**File:** `trigger/src/tasks/run-pipeline.ts`

The `executeCompanyIntelBriefing` function's success output (around line 730) currently has `target_company_domain` and `target_company_name` but NOT `domain` and `company_name`. The entity state system looks for `domain` to identify which company entity to save to. Without it, entity state resolution fails.

**Fix:** Add canonical field aliases to the success output object. Find the output block that looks like:

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
      },
```

Add two canonical alias fields:

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
        domain: targetCompanyDomain,
        company_name: targetCompanyName,
      },
```

This ensures the entity state mapper finds `domain` in cumulative context and resolves the company entity correctly.

Commit standalone with message: `fix: add canonical domain and company_name fields to company intel briefing output for entity state resolution`

---

## Deliverable 2: Person Intel Briefing Execution in `run-pipeline.ts`

**File:** `trigger/src/tasks/run-pipeline.ts`

### 2a. Add the prompt template constant

Place this after the existing `COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE` constant. The prompt is taken from `docs/api-reference-docs/parallel/person-intel-briefing-template.md`. Copy the full prompt from the `"input"` value in the Templated CURL section of that file, with placeholders intact.

The constant must be named:

```typescript
const PERSON_INTEL_BRIEFING_PROMPT_TEMPLATE = `...`;
```

The prompt has these placeholders:
- `{client_company_name}`
- `{client_company_description}`
- `{customer_company_name}`
- `{person_full_name}`
- `{person_linkedin_url}`
- `{person_current_job_title}`
- `{person_current_company_name}`
- `{person_current_company_description}`

**Copy the prompt exactly from the template file.** Shell escaping (`'\''`) becomes normal apostrophes in the TypeScript template literal.

### 2b. Add the `executePersonIntelBriefing` function

Place this after the existing `executeCompanyIntelBriefing` function. Follow the **exact same pattern** — create task, poll with `wait.for()`, fetch result, return standard result shape. The differences are:

1. **Operation ID:** `"person.derive.intel_briefing"`
2. **Prompt template:** `PERSON_INTEL_BRIEFING_PROMPT_TEMPLATE`
3. **Default processor:** `"pro"`
4. **Input fields extracted from cumulative context:**

```typescript
const clientCompanyName = String(cumulativeContext.client_company_name || "");
const clientCompanyDescription = String(cumulativeContext.client_company_description || "");
const customerCompanyName = String(cumulativeContext.customer_company_name || "");
const personFullName = String(cumulativeContext.person_full_name || cumulativeContext.full_name || "");
const personLinkedinUrl = String(cumulativeContext.person_linkedin_url || cumulativeContext.linkedin_url || "");
const personCurrentJobTitle = String(cumulativeContext.person_current_job_title || cumulativeContext.title || cumulativeContext.current_title || "");
const personCurrentCompanyName = String(cumulativeContext.person_current_company_name || cumulativeContext.current_company_name || "");
const personCurrentCompanyDescription = String(cumulativeContext.person_current_company_description || cumulativeContext.current_company_description || "");
```

5. **Required inputs check:** `clientCompanyName`, `clientCompanyDescription`, `personFullName`, and `personCurrentCompanyName` are required. If any are missing, return `status: "failed"` with `missing_inputs`.

6. **Prompt interpolation:**

```typescript
const prompt = PERSON_INTEL_BRIEFING_PROMPT_TEMPLATE
  .replaceAll("{client_company_name}", clientCompanyName)
  .replaceAll("{client_company_description}", clientCompanyDescription)
  .replaceAll("{customer_company_name}", customerCompanyName || "Not specified")
  .replaceAll("{person_full_name}", personFullName)
  .replaceAll("{person_linkedin_url}", personLinkedinUrl || "Not provided")
  .replaceAll("{person_current_job_title}", personCurrentJobTitle || "Not specified")
  .replaceAll("{person_current_company_name}", personCurrentCompanyName)
  .replaceAll("{person_current_company_description}", personCurrentCompanyDescription || "No description provided.");
```

7. **Default poll config:** `max_poll_attempts` defaults to 90 (30 minutes at 20s intervals — `pro` processor).

8. **Success output shape — include BOTH prefixed AND canonical field names:**

```typescript
output: {
  parallel_run_id: runId,
  processor,
  client_company_name: clientCompanyName,
  client_company_description: clientCompanyDescription,
  customer_company_name: customerCompanyName,
  person_full_name: personFullName,
  person_linkedin_url: personLinkedinUrl,
  person_current_job_title: personCurrentJobTitle,
  person_current_company_name: personCurrentCompanyName,
  person_current_company_description: personCurrentCompanyDescription,
  parallel_raw_response: resultData,
  full_name: personFullName,
  linkedin_url: personLinkedinUrl,
  title: personCurrentJobTitle,
}
```

The `full_name`, `linkedin_url`, and `title` fields are canonical aliases that the entity state mapper uses for person entity identity resolution.

9. **Provider attempts action name:** `"deep_research_person_intel_briefing"`

Everything else — task creation, polling loop, error handling, logging — follows `executeCompanyIntelBriefing` exactly. Do not refactor or abstract shared code.

### 2c. Add the step execution branch

In the step execution branch (around line 1307), add `person.derive.intel_briefing` as a third condition:

```typescript
let result: NonNullable<ExecuteResponseEnvelope["data"]>;
if (operationId === "company.derive.icp_job_titles") {
  result = await executeParallelDeepResearch(cumulativeContext, stepSnapshot.step_config || {});
} else if (operationId === "company.derive.intel_briefing") {
  result = await executeCompanyIntelBriefing(cumulativeContext, stepSnapshot.step_config || {});
} else if (operationId === "person.derive.intel_briefing") {
  result = await executePersonIntelBriefing(cumulativeContext, stepSnapshot.step_config || {});
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

Commit with message: `add Parallel Deep Research person intel briefing (person.derive.intel_briefing) in pipeline runner`

---

## Deliverable 3: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to the Person section (or create a Person Derive subsection):

```
| `person.derive.intel_briefing` | Parallel.ai Deep Research (direct from Trigger.dev — person intelligence briefing for outreach) |
```

Update operation count accordingly (60 total).

### File: `CLAUDE.md`

Update operation count references if present.

Commit with message: `update docs for person.derive.intel_briefing operation`

---

## What is NOT in scope

- No changes to `executeParallelDeepResearch` (the ICP job titles function) — leave it untouched
- No refactoring to share code between the three Parallel functions — keep them independent
- No FastAPI changes
- No output mapping or extraction — raw Parallel.ai response stored as-is
- No entity relationship recording (separate concern)
- No blueprint creation
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Confirmation that `domain` and `company_name` canonical fields were added to `executeCompanyIntelBriefing` output
(b) The `executePersonIntelBriefing` function signature
(c) All cumulative context fields extracted (list every alias checked for each variable)
(d) Required inputs (which fields cause failure if missing)
(e) Default processor and default max_poll_attempts
(f) Canonical alias fields in the success output (`full_name`, `linkedin_url`, `title`)
(g) The step execution branch location (exact line numbers)
(h) Error handling paths (should mirror `executeCompanyIntelBriefing`)
(i) Anything to flag
