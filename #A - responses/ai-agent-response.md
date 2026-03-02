Implemented end-to-end per docs/EXECUTOR_DIRECTIVE_INTEL_BRIEFING_TABLES.md and created the 7 standalone commits (no push).
3e155ff add 016 migration for company_intel_briefings and person_intel_briefings tables
944e1fc add service layers for company and person intel briefings
d75e2a6 add internal upsert endpoints for company and person intel briefings
76a654d add query endpoints for company and person intel briefings
ce8d7c1 add auto-persist to dedicated tables for all three Parallel Deep Research operations
175af22 add backfill scripts for company and person intel briefings
768c85b update documentation for intel briefing tables and endpoints
(a) Migration file path and both table names
Migration: supabase/migrations/016_intel_briefing_tables.sql
Tables:
company_intel_briefings
person_intel_briefings
(b) Service function signatures (all 4)
In app/services/company_intel_briefings.py:
upsert_company_intel_briefing(*, org_id: str, company_domain: str, company_name: str | None = None, client_company_name: str | None = None, client_company_description: str | None = None, raw_parallel_output: dict[str, Any], parallel_run_id: str | None = None, processor: str | None = None, source_submission_id: str | None = None, source_pipeline_run_id: str | None = None) -> dict[str, Any]
query_company_intel_briefings(*, org_id: str, company_domain: str | None = None, client_company_name: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]
In app/services/person_intel_briefings.py:
upsert_person_intel_briefing(*, org_id: str, person_full_name: str, person_linkedin_url: str | None = None, person_current_company_name: str | None = None, person_current_job_title: str | None = None, client_company_name: str | None = None, client_company_description: str | None = None, customer_company_name: str | None = None, raw_parallel_output: dict[str, Any], parallel_run_id: str | None = None, processor: str | None = None, source_submission_id: str | None = None, source_pipeline_run_id: str | None = None) -> dict[str, Any]
query_person_intel_briefings(*, org_id: str, person_linkedin_url: str | None = None, person_current_company_name: str | None = None, client_company_name: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]
(c) Internal endpoint paths
POST /api/internal/company-intel-briefings/upsert
POST /api/internal/person-intel-briefings/upsert
(d) Query endpoint paths and supported filters
POST /api/v1/company-intel-briefings/query
Filters: company_domain, client_company_name, limit, offset, org_id (super-admin path)
POST /api/v1/person-intel-briefings/query
Filters: person_linkedin_url, person_current_company_name, client_company_name, limit, offset, org_id (super-admin path)
(e) Dedup constraint fields for each table
company_intel_briefings: (org_id, company_domain, client_company_name)
person_intel_briefings: (org_id, person_full_name, person_current_company_name, client_company_name)
(f) All three auto-persist blocks (confirmation)
In trigger/src/tasks/run-pipeline.ts, immediately before cumulativeContext = mergeContext(...), all three blocks are present and follow the requested non-fatal pattern:
operationId === "company.derive.icp_job_titles" with gate result.status === "found" && result.output, wrapped in try/catch
operationId === "company.derive.intel_briefing" with gate result.status === "found" && result.output, wrapped in try/catch
operationId === "person.derive.intel_briefing" with gate result.status === "found" && result.output, wrapped in try/catch
(g) Backfill scripts: paths, submission IDs, run command
scripts/backfill_company_intel_briefings.py
Submission IDs:
b8001673-d0a4-4c4f-824a-9904964d8400
5d1cb2b3-bbf9-4582-a29f-3167d22dec51
31484f3a-5285-42ad-a8a9-892e79e9eabe
scripts/backfill_person_intel_briefings.py
Submission ID:
35d818c4-2159-4e5d-89a7-dddf92470c57
Run commands:
doppler run -p data-engine-x-api -c prd -- uv run python scripts/backfill_company_intel_briefings.py
doppler run -p data-engine-x-api -c prd -- uv run python scripts/backfill_person_intel_briefings.py
(h) Anything to flag
Unrelated pre-existing workspace changes were present (docs/api-reference-docs, trigger/package*.json, and many untracked files); I did not modify or include them in these commits.
I did not run migrations or backfills (per scope and safety); these remain manual.
Lint check on edited code files returned no errors.