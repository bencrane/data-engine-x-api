Implemented end-to-end per the directive, with 3 separate commits and no push.
fbfb779 — fix: add canonical domain and company_name fields to company intel briefing output for entity state resolution
6046990 — add Parallel Deep Research person intel briefing (person.derive.intel_briefing) in pipeline runner
4565206 — update docs for person.derive.intel_briefing operation
(a) Canonical fields added to executeCompanyIntelBriefing output
Yes. Added:
domain: targetCompanyDomain
company_name: targetCompanyName
in trigger/src/tasks/run-pipeline.ts (output block now includes both prefixed and canonical aliases).
(b) executePersonIntelBriefing function signature
async function executePersonIntelBriefing(cumulativeContext: Record<string, unknown>, stepConfig: Record<string, unknown>): Promise<NonNullable<ExecuteResponseEnvelope["data"]>>
(c) Cumulative context fields extracted (all aliases)
clientCompanyName: client_company_name
clientCompanyDescription: client_company_description
customerCompanyName: customer_company_name
personFullName: person_full_name OR full_name
personLinkedinUrl: person_linkedin_url OR linkedin_url
personCurrentJobTitle: person_current_job_title OR title OR current_title
personCurrentCompanyName: person_current_company_name OR current_company_name
personCurrentCompanyDescription: person_current_company_description OR current_company_description
(d) Required inputs (fail if missing)
client_company_name
client_company_description
person_full_name (resolved via person_full_name || full_name)
person_current_company_name (resolved via person_current_company_name || current_company_name)
If missing, returns status: "failed" with missing_inputs.
(e) Defaults
Default processor: "pro"
Default max_poll_attempts: 90
Default poll interval: 20 seconds
(f) Canonical alias fields in success output
Yes, added to person success output:
full_name
linkedin_url
title
(g) Step execution branch location (exact line numbers)
In trigger/src/tasks/run-pipeline.ts:
1742: } else if (operationId === "person.derive.intel_briefing") {
1743: result = await executePersonIntelBriefing(cumulativeContext, stepSnapshot.step_config || {});
(h) Error handling paths (mirrors company intel briefing)
executePersonIntelBriefing mirrors executeCompanyIntelBriefing pattern:
missing PARALLEL_API_KEY → failed/skipped provider attempt
missing required inputs → failed + missing_inputs
task creation non-OK → failed + task_creation_failed
task creation exception → failed + task_creation_exception
polling non-OK/exception logs warn and continues
terminal task failed → failed + parallel_task_failed
poll timeout → failed + poll_timeout
result fetch non-OK → failed + result_fetch_failed
result fetch exception → failed + result_fetch_exception
success → status: "found" with output + provider attempt metadata
(i) Anything to flag
CLAUDE.md has no operation-count references to update, so no changes were needed there.
Worktree still contains unrelated pre-existing modifications/untracked files outside this directive (left untouched).