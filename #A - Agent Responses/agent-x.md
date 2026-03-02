Implemented and committed in one commit: e682f4e.
File changed: trigger/src/tasks/run-pipeline.ts
Docs: no changes made to docs/SYSTEM_OVERVIEW.md or CLAUDE.md (per directive)
run-pipeline.ts
Lines 1755-1782
if (operationId === "company.derive.icp_job_titles" && result.status === "found" && result.output) {  try {    await internalPost(internalConfig, "/api/internal/icp-job-titles/upsert", {      company_domain: result.output.domain || result.output.company_domain,      company_name: result.output.company_name,      company_description: result.output.company_description,      raw_parallel_output:        (result.output.parallel_raw_response as Record<string, unknown>)?.output?.content ||        result.output.parallel_raw_response,      parallel_run_id: result.output.parallel_run_id,      processor: result.output.processor,      source_submission_id: run.submission_id,      source_pipeline_run_id: pipeline_run_id,    });    logger.info("ICP job titles persisted to dedicated table", {      domain: result.output.domain || result.output.company_domain,      company_name: result.output.company_name,      pipeline_run_id,    });  } catch (error) {    logger.warn("Failed to persist ICP job titles to dedicated table", {      pipeline_run_id,      error: error instanceof Error ? error.message : String(error),    });  }}
(a) Exact inserted lines: 1755 through 1780 in trigger/src/tasks/run-pipeline.ts (immediately before mergeContext at 1782).
(b) Upsert gate condition:
operationId === "company.derive.icp_job_titles" && result.status === "found" && result.output
(c) raw_parallel_output extraction path:
Reads result.output.parallel_raw_response.output.content first, falls back to result.output.parallel_raw_response.
(d) Failure isolation confirmation:
Yes — the persistence call is wrapped in a local try/catch; failures only emit logger.warn("Failed to persist ICP job titles to dedicated table", ...) and do not fail the pipeline step.
(e) Anything to flag:
Repo has many unrelated pre-existing modified/untracked files; commit includes only trigger/src/tasks/run-pipeline.ts.
Lint check on edited file returned clean.