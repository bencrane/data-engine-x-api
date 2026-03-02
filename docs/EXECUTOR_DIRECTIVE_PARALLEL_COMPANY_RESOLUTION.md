# Directive: `company.resolve.domain_from_name_parallel` — Parallel.ai Company Resolution

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** When the HQ company name lookup doesn't find a match, we fall back to Parallel.ai to resolve a company name to its domain and LinkedIn URL. This uses Parallel's structured task API with `lite` processor (fast, cheap). Like the existing Parallel.ai operations (`company.derive.icp_job_titles`, `company.derive.intel_briefing`), this runs directly from Trigger.dev — NOT through FastAPI — because it's an async task with polling.

The input comes from Sales Navigator scrape results: `current_company_name`, `current_company_industry`, `current_company_location` from the prospect's cumulative context.

---

## Existing code to read before starting

- `trigger/src/tasks/run-pipeline.ts` — **critical**. Read `executeParallelDeepResearch` (~line 384) for the exact pattern: API key check, create task, poll loop with `wait.for`, fetch result, error handling. Your new function follows this same structure but with these differences:
  - Uses `task_spec` with structured input/output schemas instead of a raw `input` prompt
  - Uses `lite` processor instead of `pro`
  - Shorter poll intervals (10 seconds instead of 20) and fewer max attempts (30 instead of 90) because `lite` is fast
  - Parses structured JSON output instead of raw text

Also read the operation dispatch block (~line 1750) to see how Parallel operations are routed, and the auto-persist blocks (~line 1767) for the persistence pattern.

---

## Parallel.ai API Reference

**Create task:**
```
POST https://api.parallel.ai/v1/tasks/runs
Headers: x-api-key: {PARALLEL_API_KEY}
```

**Request body:**
```json
{
  "input": "{\"company_name\": \"Datadog\", \"industry\": \"Technology, Information and Internet\", \"location\": \"New York, NY\"}",
  "processor": "lite",
  "task_spec": {
    "input_schema": {
      "json_schema": {
        "properties": {
          "company_name": {
            "description": "The name of the company to find the domain and LinkedIn URL for.",
            "type": "string"
          },
          "industry": {
            "description": "The industry of the company to find the domain and LinkedIn URL for.",
            "type": "string"
          },
          "location": {
            "description": "The location of the company to find the domain and LinkedIn URL for.",
            "type": "string"
          }
        },
        "type": "object"
      },
      "type": "json"
    },
    "output_schema": {
      "json_schema": {
        "additionalProperties": false,
        "properties": {
          "company_domain": {
            "description": "The primary internet domain name for the company (e.g., 'example.com'). If the domain cannot be found, return null.",
            "type": "string"
          },
          "company_linkedin_url": {
            "description": "The official LinkedIn profile URL for the company. If the LinkedIn URL cannot be found, return null.",
            "type": "string"
          }
        },
        "required": ["company_domain", "company_linkedin_url"],
        "type": "object"
      },
      "type": "json"
    }
  }
}
```

**Important:** The `input` field is a JSON **string** — stringify the input object before sending.

**Poll status:**
```
GET https://api.parallel.ai/v1/tasks/runs/{run_id}
Headers: x-api-key: {PARALLEL_API_KEY}
Response: { "status": "queued" | "running" | "completed" | "failed" }
```

**Fetch result:**
```
GET https://api.parallel.ai/v1/tasks/runs/{run_id}/result
Headers: x-api-key: {PARALLEL_API_KEY}
Response: { "output": { "content": "{\"company_domain\": \"datadoghq.com\", \"company_linkedin_url\": \"https://www.linkedin.com/company/datadog\"}" } }
```

The output `content` is a JSON **string** that needs to be parsed. The parsed object contains `company_domain` and `company_linkedin_url`.

---

## Deliverable 1: Parallel Company Resolution Function

**File:** `trigger/src/tasks/run-pipeline.ts`

Add a new async function near the existing `executeParallelDeepResearch`:

```typescript
async function executeParallelCompanyResolution(
  cumulativeContext: Record<string, unknown>,
  stepConfig: Record<string, unknown>,
): Promise<NonNullable<ExecuteResponseEnvelope["data"]>>
```

**Operation ID:** `"company.resolve.domain_from_name_parallel"`

**Input extraction from cumulative context:**
```typescript
const companyName = String(
  cumulativeContext.current_company_name ||
  cumulativeContext.company_name ||
  cumulativeContext.canonical_name ||
  ""
);
const industry = String(
  cumulativeContext.current_company_industry ||
  cumulativeContext.industry ||
  ""
);
const location = String(
  cumulativeContext.current_company_location ||
  cumulativeContext.geo_region ||
  ""
);
```

`current_company_name`, `current_company_industry`, `current_company_location` are the field names from `_map_person` in the Sales Nav scraper — these are in cumulative context after fan-out from step 1.

**Required:** `companyName`. If empty → return failed with `missing_inputs: ["company_name"]`.

**API key:** `process.env.PARALLEL_API_KEY` (already in Trigger.dev env vars).

**Task creation:**
- Processor: `"lite"` (override from `stepConfig.processor` if present)
- `input`: `JSON.stringify({ company_name: companyName, industry: industry || undefined, location: location || undefined })` — only include industry/location if non-empty
- `task_spec`: the exact schema from the API reference above. This is a static object — define it as a const above the function.

**Poll configuration:**
- `maxPollAttempts`: from `stepConfig.max_poll_attempts` or default `30`
- `pollIntervalSeconds`: from `stepConfig.poll_interval_seconds` or default `10`
- Uses `wait.for({ seconds: pollIntervalSeconds })` same as existing Parallel functions

**Result parsing:**
The result response has `output.content` as a JSON string. Parse it:
```typescript
const resultData = (await resultResponse.json()) as Record<string, unknown>;
const outputObj = resultData.output as Record<string, unknown> | undefined;
const contentStr = String(outputObj?.content || "{}");
let parsed: Record<string, unknown>;
try {
  parsed = JSON.parse(contentStr);
} catch {
  parsed = {};
}
```

**Return on success:**
```typescript
{
  run_id: crypto.randomUUID(),
  operation_id: "company.resolve.domain_from_name_parallel",
  status: "found",
  output: {
    company_domain: parsed.company_domain || null,
    company_linkedin_url: parsed.company_linkedin_url || null,
    parallel_run_id: runId,
    processor: "lite",
    source_company_name: companyName,
    source_provider: "parallel",
  },
  provider_attempts: [
    {
      provider: "parallel",
      action: "resolve_company_domain",
      status: "found",
      parallel_run_id: runId,
      processor: "lite",
      poll_count: pollCount,
    },
  ],
}
```

If `parsed.company_domain` is null/empty, set status to `"not_found"` instead of `"found"`.

**Error handling:** Follow the exact same pattern as `executeParallelDeepResearch` — separate error returns for task creation failure, poll timeout, task failure, result fetch failure. Each returns the operation_id and appropriate error metadata.

Commit standalone with message: `add Parallel.ai company resolution function in pipeline runner`

---

## Deliverable 2: Operation Dispatch Wiring

**File:** `trigger/src/tasks/run-pipeline.ts`

In the operation dispatch block (~line 1750), add the new operation alongside the existing Parallel operations:

```typescript
} else if (operationId === "company.resolve.domain_from_name_parallel") {
  result = await executeParallelCompanyResolution(cumulativeContext, stepSnapshot.step_config || {});
}
```

Place it after the existing `person.derive.intel_briefing` dispatch and before the `else` block that calls `callExecuteV1`.

Commit standalone with message: `wire company.resolve.domain_from_name_parallel into pipeline runner dispatch`

---

## Deliverable 3: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to Resolution / CRM Cleanup section:
```
| `company.resolve.domain_from_name_parallel` | Parallel.ai lite (resolve company domain + LinkedIn URL from name, direct from Trigger.dev) |
```

Update operation count.

### File: `CLAUDE.md`

Update `run-pipeline.ts` description to mention 4 Parallel.ai direct operations (was 3).

Commit standalone with message: `update documentation for company.resolve.domain_from_name_parallel operation`

---

## What is NOT in scope

- No FastAPI changes — this operation runs entirely in Trigger.dev
- No database migrations
- No new provider adapters in Python
- No deploy commands
- No changes to existing Parallel.ai functions

## Trigger.dev Deploy Note

This directive modifies `trigger/src/tasks/run-pipeline.ts`. After the chief agent reviews and pushes, a Trigger.dev deploy is required:
```bash
cd trigger && npx trigger.dev@4.4.0 deploy
```

This must happen AFTER the Railway deploy (if any FastAPI changes are in the same push).

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Function signature and the Parallel.ai endpoint it calls
(b) Input extraction — confirm `current_company_name`, `current_company_industry`, `current_company_location` are the primary aliases
(c) Task spec — confirm structured input/output schemas match the reference above exactly
(d) Processor used (`lite`) and poll config (interval, max attempts)
(e) Output fields — confirm `company_domain` and `company_linkedin_url` are top-level in output
(f) How `output.content` JSON string is parsed
(g) Dispatch wiring location in the operation routing block
(h) Anything to flag
