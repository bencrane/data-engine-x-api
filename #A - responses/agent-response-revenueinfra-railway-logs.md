’ll trace the failing request through the code and match it to the Railway traceback so we can pinpoint the exact throwing line and root cause without changing anything.
I found the stack frame and it points to persistence, not the provider call; I’m now confirming the schema constraint and the job-output contract to finalize exact root cause.
Diagnosis
POST /api/v1/execute for operation_id: "job.validate.is_active" is failing after the provider call, during DB persistence.
Exact exception and throw site
Exception type: postgrest.exceptions.APIError (Postgres error code 23514)
Thrown from: postgrest/_sync/request_builder.py, line 53, while executing insert
App frame where it propagates: app/services/operation_history.py, line 50 (client.table("operation_runs").insert(run_row).execute())
Caller frame: app/routers/execute_v1.py, line 664 (inside job.validate.is_active branch)
The Railway log message is explicit:
new row for relation "operation_runs" violates check constraint "operation_runs_entity_type_check"
failing row includes operation_id = job.validate.is_active and entity_type = job
Execution-path trace (requested)
app/routers/execute_v1.py dispatches job.validate.is_active
Calls execute_job_validate_is_active(...) in app/services/research_operations.py
That calls validate_job_active(...) in app/providers/revenueinfra/validate_job.py
Provider returns mapped payload; JobValidationOutput.model_validate(...) runs in execute_job_validate_is_active and succeeds
Back in router, persist_operation_execution(...) runs
Insert into operation_runs fails on entity_type check constraint
Root cause
operation_runs.entity_type is still constrained to only ('company', 'person') in migration supabase/migrations/005_operation_execution_history.sql:
entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person'))
job was introduced elsewhere (e.g. migration 013 updates entity_timeline and entity_snapshots), but not operation_runs.
What fix is needed (diagnosis only)
Schema migration to update operation_runs_entity_type_check to allow job:
CHECK (entity_type IN ('company', 'person', 'job'))
That is the blocking defect causing the 500. The provider path/auth path are not the failing components in this trace.