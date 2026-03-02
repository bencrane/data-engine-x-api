Implemented exactly in-scope with two commits and no deploy actions:
b012184 — add Parallel Deep Research execution for company.derive.icp_job_titles in pipeline runner
6babd40 — update docs for company.derive.icp_job_titles operation
(a) wait import path that worked
@trigger.dev/sdk/v3 worked (dist/esm/v3/index.d.ts exports ./wait.js).
(b) executeParallelDeepResearch signature
async function executeParallelDeepResearch(cumulativeContext: Record<string, unknown>, stepConfig: Record<string, unknown>): Promise<NonNullable<ExecuteResponseEnvelope["data"]>>
(c) Cumulative-context fields used for prompt interpolation (aliases checked)
company_name: cumulativeContext.company_name or cumulativeContext.companyName
domain: cumulativeContext.domain or cumulativeContext.company_domain
company_description: cumulativeContext.company_description or cumulativeContext.description (fallback text: "No description provided.")
(d) Success result shape (output fields)
parallel_run_id
processor
company_name
domain
company_description
parallel_raw_response
(e) Step execution branch location (exact line numbers before/after)
Before (original call path): run-pipeline.ts lines 638–646 (your referenced block).
After (new branch): run-pipeline.ts lines 922–935.
if (operationId === "company.derive.icp_job_titles") at line 924.
New helper location: executeParallelDeepResearch starts at line 147.
(f) Error handling paths and resulting status/error semantics
Missing PARALLEL_API_KEY
status: "failed"
provider_attempts[0].status: "skipped"
skip_reason: "missing_parallel_api_key"
Missing required prompt inputs (company_name and/or domain)
status: "failed"
missing_inputs: [...]
provider_attempts: []
Task creation non-OK response
status: "failed"
provider_attempts[0].status: "failed"
error: "task_creation_failed: <http_status>" + raw_response
Task creation exception
status: "failed"
error: "task_creation_exception: <message>"
Poll loop status becomes failed
status: "failed"
error: "parallel_task_failed"
includes parallel_run_id, poll_count
Poll timeout (never reaches completed/failed within max attempts)
status: "failed"
error: "poll_timeout"
includes parallel_run_id, poll_count, max_poll_attempts
Result fetch non-OK response
status: "failed"
error: "result_fetch_failed: <http_status>" + raw_response + parallel_run_id
Result fetch exception
status: "failed"
error: "result_fetch_exception: <message>" + parallel_run_id
(g) Anything to flag
There are unrelated pre-existing/unrelated working-tree changes outside this scope (including docs/api-reference-docs and local trigger/package*.json modifications visible in git status). I did not stage or commit any of those.
docs/SYSTEM_OVERVIEW.md now reflects:
Operations (58 live)
Company Derive (3) with company.derive.icp_job_titles
Operation registry (58 ops)