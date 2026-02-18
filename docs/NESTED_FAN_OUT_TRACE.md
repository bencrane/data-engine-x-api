# Nested Fan-Out Trace

This note documents the current nested fan-out execution path and confirms recursion support in the existing architecture.

## Verified Call Path

1. `create_fan_out_child_pipeline_runs(...)` creates child `pipeline_runs` with:
   - `parent_pipeline_run_id` set to the current run
   - full `blueprint_snapshot.steps`
   - `blueprint_snapshot.fan_out.start_from_position` set to the next step position
2. `run-pipeline` reads `getExecutionStartPosition(...)` and executes from `start_from_position`.
3. If a later step in that child run has `fan_out: true`, `run-pipeline` executes the same fan-out block again.
4. That block posts to `POST /api/internal/pipeline-runs/fan-out` with:
   - `parent_pipeline_run_id` equal to the *child* run ID
   - `start_from_position` set to current step + 1
5. `/api/internal/pipeline-runs/fan-out` validates tenancy/submission and calls
   `create_fan_out_child_pipeline_runs(...)` again, producing grandchild runs.

Because the internal fan-out API validates by tenancy/submission and does not restrict parent depth, recursion works for parent -> child -> grandchild and beyond.

## Example Scenario

Blueprint steps:

1. `company.research.lookup_customers` (`fan_out: true`)
2. `company.enrich.profile`
3. `person.search` (`fan_out: true`)
4. `person.contact.resolve_email`

Expected run graph:

- Root run executes step 1 and fans out to customer child runs starting at step 2.
- Each child run executes steps 2-3.
- Step 3 in each child run fans out to person grandchild runs starting at step 4.
- Each grandchild run executes step 4.

This flow is supported by the current recursive fan-out path.
