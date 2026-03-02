Implemented and committed in two commits, no deploys, no FastAPI changes, no refactors.
53e2321 — add Parallel Deep Research company intel briefing (company.derive.intel_briefing) in pipeline runner
7595559 — update docs for company.derive.intel_briefing operation
(a) executeCompanyIntelBriefing function signature
async function executeCompanyIntelBriefing(cumulativeContext: Record<string, unknown>, stepConfig: Record<string, unknown>): Promise<NonNullable<ExecuteResponseEnvelope["data"]>>
(b) Cumulative context fields extracted (with full alias chains)
clientCompanyName: client_company_name
clientCompanyDescription: client_company_description
targetCompanyName: target_company_name → company_name
targetCompanyDomain: target_company_domain → domain
targetCompanyDescription: target_company_description → company_description → description
targetCompanyIndustry: target_company_industry → industry
targetCompanySize: target_company_size → employee_count → employee_range
targetCompanyFunding: target_company_funding → funding
targetCompanyCompetitors: target_company_competitors
(c) Required inputs (fail if missing)
client_company_name
client_company_description
target_company_name (resolved from target/company alias chain above)
target_company_domain (resolved from target/domain alias chain above)
(d) Defaults
processor: "ultra"
max_poll_attempts: 135
poll_interval_seconds: 20 (same as existing pattern)
(e) Success output fields
parallel_run_id
processor
client_company_name
client_company_description
target_company_name
target_company_domain
target_company_description
target_company_industry
target_company_size
target_company_funding
parallel_raw_response
(f) Step execution branch location (exact line numbers)
In trigger/src/tasks/run-pipeline.ts, branch now sits at:
1308 declaration of result
1309-1310 company.derive.icp_job_titles
1311-1312 company.derive.intel_briefing
1313-1321 fallback callExecuteV1
(g) Error handling paths in executeCompanyIntelBriefing (mirrors executeParallelDeepResearch)
Missing PARALLEL_API_KEY → failed with provider attempt status: "skipped" + skip_reason: "missing_parallel_api_key"
Missing required inputs → failed with missing_inputs, empty provider_attempts
Task create HTTP non-OK → failed, error: task_creation_failed:<status>, includes raw_response
Task create exception → failed, error: task_creation_exception:<message>
Poll terminal status failed → failed, error: "parallel_task_failed", includes parallel_run_id, poll_count
Poll timeout (taskStatus !== completed after max polls) → failed, error: "poll_timeout", includes parallel_run_id, poll_count, max_poll_attempts
Result fetch HTTP non-OK → failed, error: result_fetch_failed:<status>, includes raw_response, parallel_run_id
Result fetch exception → failed, error: result_fetch_exception:<message>, includes parallel_run_id
Poll status non-OK or exception during loop is logged and retried (does not immediately fail), same as existing function behavior
(h) Anything to flag
docs/api-reference-docs is currently modified in the working tree (pre-existing/unrelated), plus other unrelated dirty/untracked files; neither requested commit touched them.
CLAUDE.md has no operation-count reference to update, so Deliverable 2 only required docs/SYSTEM_OVERVIEW.md.