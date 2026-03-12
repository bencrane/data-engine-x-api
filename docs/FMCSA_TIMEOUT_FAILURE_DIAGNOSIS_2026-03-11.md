# FMCSA Run Failure Diagnosis (2026-03-11)

## Scope

Diagnose why many manually triggered FMCSA runs in Trigger.dev production ended as `TIMED_OUT`, `FAILED`, or `CRASHED`, especially after setting FMCSA task timeout to 12 hours in local code.

This is diagnosis only. No fixes were applied.

## Data Reviewed

- Trigger.dev production runs (`v20260311.7`) triggered today for the 29 FMCSA tasks (excluding company census + vehicle inspection file per request).
- Trigger.dev run details for representative failed/timed-out/crashed runs.
- Current worker metadata (`prod` worker version `20260311.7`).
- Local workflow/task source:
  - `trigger/src/tasks/fmcsa-*.ts`
  - `trigger/src/workflows/fmcsa-daily-diff.ts`
  - `trigger/src/workflows/internal-api.ts`

## High-Confidence Findings

### 1) The `TIMED_OUT` runs are platform max-duration timeouts, not CSV/parser timeouts

For timed-out runs, Trigger.dev reports:

- `Error: trigger.dev internal error (MAX_DURATION_EXCEEDED)`
- status `timed out`

Examples:

- `run_cmmmeqxaw6tvo0on1a0qrjq4a` (`fmcsa-sms-input-violation-daily`)
- `run_cmmmeqxbx6tfs0in1negzxd8a` (`fmcsa-sms-motor-carrier-census-daily`)
- `run_cmmmeqxai6via0pofnyocbk9l` (`fmcsa-sms-input-inspection-daily`)
- `run_cmmmeqnh26tcc0in1nckkmab4` (`fmcsa-sms-c-passproperty-daily`)

This confirms the timeout classification is Trigger runtime max-duration enforcement.

### 2) The 12-hour timeout change is present locally, but production runs are on deployed worker `v20260311.7`

Current local source now shows `maxDuration: 43200` for FMCSA tasks (except company census + vehicle inspection file at `10800`).

However, the runs in question executed on deployed worker version `20260311.7` in prod.  
If that deployed worker does not include the new timeout settings, Trigger will continue using older task max-duration limits.

Practical implication: updating task timeout in repo does not affect live runs until a Trigger deploy publishes a new worker version.

### 3) Many `FAILED` runs are caused by internal API write pressure/failures, independent of task max-duration

Representative errors:

- `InternalApiTimeoutError: Internal API request timed out after 30000ms: /api/internal/.../upsert-batch`
  - Seen in `fmcsa-carrier-daily`, `fmcsa-inshist-daily`, `fmcsa-boc3-daily`, etc.
- `InternalApiError: Internal API request failed (500): /api/internal/operating-authority-revocations/upsert-batch`
  - Seen in `fmcsa-revocation-all-history-daily`.
- `InternalApiError: ... (502)` on first attempt for `fmcsa-sms-ab-pass-daily` (then succeeded on retry).

These are backend write-path failures/timeouts during batch upsert confirmation, not Trigger max-duration events.

### 4) `CRASHED` runs are OOM terminations

Representative errors:

- `TASK_PROCESS_OOM_KILLED: Run was terminated due to running out of memory`

Seen in:

- `fmcsa-actpendinsur-all-history`
- `fmcsa-boc3-all-history`
- `fmcsa-inshist-all-history`
- `fmcsa-authhist-all-history`

This is a memory exhaustion issue in task execution.

## Secondary Technical Context (from code)

The FMCSA workflow applies additional operation-level timeouts that can fail runs even when task max-duration is long:

- Internal API default timeout: `30_000ms` (`internal-api.ts`)
- Streaming CSV default download timeout: `300_000ms` (`fmcsa-daily-diff.ts`)
- Streaming CSV default persistence timeout: `120_000ms` (`fmcsa-daily-diff.ts`)
- Some feeds override with longer stream/persist timeouts (`3_300_000ms` / `300_000ms`)

So there are at least two separate timeout layers:

1. Trigger task max-duration (run-level)
2. Internal request/download/persistence timeouts (operation-level)

## Current Outcome Snapshot (for the 29 triggered runs)

- `TIMED_OUT`: 6
- `FAILED`: 8
- `CRASHED`: 4
- `COMPLETED`: 3
- `EXECUTING` (still running at collection time): 8

## Direct Answer to "how can it time out if we set 12 hours?"

Because the observed `TIMED_OUT` runs are coming from the deployed production worker config (`v20260311.7`) enforcing max-duration (`MAX_DURATION_EXCEEDED`), while your 12-hour task timeout edits are in local source and are not automatically active in prod until deployed.  

Also, even with a 12-hour task max-duration, many runs can still fail earlier due to internal API/download/persistence timeout limits and OOM conditions.

