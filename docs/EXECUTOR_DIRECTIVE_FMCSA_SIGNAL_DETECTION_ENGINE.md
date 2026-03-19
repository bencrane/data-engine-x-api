# Executor Directive: FMCSA Signal Detection Engine

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA ingestion pipeline stores faithful daily observations of federal motor carrier data across 18 tables. The business payoff is answering: *what changed today?* This directive builds the signal detection engine — the daily diff layer that compares today's snapshot against yesterday's and emits actionable business signals (new carriers, revoked authorities, lapsed insurance, safety score deterioration, new crashes, etc.). These signals are the primary outbound trigger for insurance brokers, compliance vendors, safety consultants, and fleet management companies.

---

## Reference Documents (Read Before Starting)

**Must read — project conventions:**
- `CLAUDE.md` — project conventions, deploy protocol, auth model, schema location (`entities` schema)

**Must read — existing query patterns (follow these):**
- `app/services/fmcsa_carrier_query.py` — connection pool pattern, latest-snapshot CTE pattern, parameterized query approach, `_get_pool()` lazy init
- `app/services/fmcsa_carrier_detail.py` — multi-table carrier profile aggregation, Decimal coercion

**Must read — table schemas (these are the source tables for diff queries):**
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql` — `operating_authority_histories`, `operating_authority_revocations`, `insurance_policies` (fingerprint-based tables with `first_observed_at`/`last_observed_at`, no `feed_date`)
- `supabase/migrations/024_fmcsa_sms_tables.sql` — `carrier_safety_basic_percentiles` (feed-date-based, `UNIQUE(feed_date, source_feed_name, row_position)`)
- `supabase/migrations/025_fmcsa_remaining_csv_export_tables.sql` — `motor_carrier_census_records`, `commercial_vehicle_crashes`, `out_of_service_orders` (feed-date-based)

**Must read — internal endpoint pattern:**
- `app/routers/internal.py` — `require_internal_key` auth dependency (line 66), request model patterns, `DataEnvelope` responses

**Must read — Trigger.dev task patterns:**
- `trigger/src/workflows/internal-api.ts` — `InternalApiClient`, `createInternalApiClient`, `resolveInternalApiConfig`
- `trigger/src/tasks/` — any existing scheduled task for reference on `schedules.task` usage and cron syntax

---

## Critical Design Decisions

### Two Table Identity Patterns

The FMCSA tables use two different identity patterns. The diff logic must handle both:

**Pattern A — Feed-date-based tables** (migrations 024, 025): `motor_carrier_census_records`, `carrier_safety_basic_percentiles`, `commercial_vehicle_crashes`, `out_of_service_orders`. These have `feed_date` and `row_position` columns. The diff compares the two most recent `feed_date` values for each table: rows in today's snapshot not in yesterday's (or vice versa), or value changes between snapshots for the same carrier.

**Pattern B — Fingerprint-based tables** (migration 022): `operating_authority_histories`, `operating_authority_revocations`, `insurance_policies`. These have `record_fingerprint` (unique), `first_observed_at`, and `last_observed_at` but NO `feed_date`. The diff uses `first_observed_at` and `last_observed_at` relative to the most recent `source_observed_at` value: newly appeared records have `first_observed_at` matching the latest observation window; disappeared records have `last_observed_at` older than the latest observation.

### Idempotency

Running signal detection twice for the same feed date must produce the same result, not duplicates. The `fmcsa_carrier_signals` table uses a UNIQUE constraint on `(signal_type, feed_date, entity_key)`. Persistence uses `INSERT ... ON CONFLICT DO NOTHING` (or `DO UPDATE` if enrichment fields should refresh).

### Signal Enrichment

Each signal row carries enough context to be actionable without a second query. The detection service joins to `motor_carrier_census_records` (latest snapshot) to populate `legal_name`, `physical_state`, `power_unit_count`, and `driver_total` for every signal. For signals that don't naturally have a `dot_number` (e.g., insurance by docket), resolve `dot_number` via the `carrier_registrations` table (`docket_number → usdot_number`).

---

## Signal Types

Nine signal types to detect. The `signal_type` column uses these exact string values:

| signal_type | Source Table | Pattern | Severity Logic |
|---|---|---|---|
| `new_carrier` | motor_carrier_census_records | A (feed_date) | `info` |
| `disappeared_carrier` | motor_carrier_census_records | A (feed_date) | `warning` |
| `authority_granted` | operating_authority_histories | B (fingerprint) | `info` |
| `authority_revoked` | operating_authority_revocations | B (fingerprint) | `warning` |
| `insurance_added` | insurance_policies | B (fingerprint) | `info` |
| `insurance_lapsed` | insurance_policies | B (fingerprint) | `critical` if BIPD coverage, else `warning` |
| `safety_worsened` | carrier_safety_basic_percentiles | A (feed_date) | `critical` if any percentile crossed 90th; `warning` if crossed 75th |
| `new_crash` | commercial_vehicle_crashes | A (feed_date) | `critical` if fatalities > 0; `warning` otherwise |
| `new_oos_order` | out_of_service_orders | A (feed_date) | `critical` |

### Detection Logic Per Signal Type

**`new_carrier`**: DOT numbers present in today's `motor_carrier_census_records` snapshot (max `feed_date`) that do NOT exist in yesterday's snapshot (second-max `feed_date`). Compare on `dot_number`. `entity_key` = `dot_number`. `after_values` should include key census fields (operation code, state, fleet size).

**`disappeared_carrier`**: DOT numbers in yesterday's snapshot NOT in today's. `entity_key` = `dot_number`. `before_values` should include the carrier's last known census fields.

**`authority_granted`**: New rows in `operating_authority_histories` where `first_observed_at` falls within the detection window AND the `final_authority_action_description` (or `original_authority_action_description`) indicates a grant (e.g., contains 'GRANT'). `entity_key` = `record_fingerprint`. `dot_number` = `usdot_number`. `after_values` = authority type, action description, dates.

**`authority_revoked`**: New rows in `operating_authority_revocations` where `first_observed_at` falls within the detection window. `entity_key` = `record_fingerprint`. `dot_number` = `usdot_number`. `after_values` = revocation type, serve date, effective date.

**`insurance_added`**: New rows in `insurance_policies` where `first_observed_at` falls within the detection window AND `is_removal_signal = FALSE`. `entity_key` = `record_fingerprint`. Resolve `dot_number` from `docket_number` via `carrier_registrations`. `after_values` = insurance type, BIPD limits, policy number, effective date, insurer.

**`insurance_lapsed`**: Records in `insurance_policies` where `is_removal_signal = TRUE` AND `first_observed_at` falls within the detection window. Also: records whose `last_observed_at` is older than the latest `source_observed_at` for insurance feeds (present in previous observation but not current). `entity_key` = `record_fingerprint`. `before_values` = the lapsed policy details.

**`safety_worsened`**: Compare each carrier's percentile values between the two most recent `feed_date` snapshots in `carrier_safety_basic_percentiles`. Flag carriers where ANY of the 5 BASIC percentiles (unsafe_driving, hours_of_service, driver_fitness, controlled_substances_alcohol, vehicle_maintenance) increased materially. Thresholds: emit a signal when a percentile crosses above 75 or above 90 (was below, now above). Generate one signal per carrier per threshold crossing (not one per BASIC category — roll up into a single signal with all worsened categories in `signal_details`). `entity_key` = `dot_number`. `before_values` = previous percentiles. `after_values` = current percentiles. `signal_details` = list of which BASICs worsened and by how much.

**`new_crash`**: Crash rows in today's `commercial_vehicle_crashes` snapshot (max `feed_date`) not in yesterday's, matched by `crash_id`. `entity_key` = `crash_id`. `after_values` = report date, state, city, fatalities, injuries, tow_away, hazmat_released.

**`new_oos_order`**: Rows in today's `out_of_service_orders` snapshot (max `feed_date`) not in yesterday's, matched on `(dot_number, oos_date, oos_reason)`. `entity_key` = `dot_number:oos_date`. `after_values` = oos_date, oos_reason, status.

### Detection Window

For Pattern A tables: the two most recent `feed_date` values in that table.

For Pattern B tables: the detection window is the time range between the two most recent distinct `source_observed_at` values for each table. "New" = `first_observed_at >= latest_source_observed_at`. "Disappeared" = `last_observed_at < latest_source_observed_at AND last_observed_at >= previous_source_observed_at`.

---

## File Structure

Create these new files:

| File | Purpose |
|---|---|
| `supabase/migrations/035_fmcsa_carrier_signals.sql` | Signal table in entities schema |
| `app/services/fmcsa_signal_detection.py` | Diff query functions + detection orchestrator |
| `trigger/src/tasks/fmcsa-signal-detection.ts` | Scheduled Trigger.dev task |
| `tests/test_fmcsa_signal_detection.py` | Tests for detection service |

Modify this existing file:

| File | Change |
|---|---|
| `app/routers/internal.py` | Add `POST /fmcsa-signals/detect` endpoint |

---

## Deliverable 1: Schema Migration

Create `supabase/migrations/035_fmcsa_carrier_signals.sql`.

**Table:** `entities.fmcsa_carrier_signals`

**Columns:**
- `id` UUID PRIMARY KEY DEFAULT gen_random_uuid()
- `signal_type` TEXT NOT NULL — one of the 9 values above
- `feed_date` DATE NOT NULL — the feed date this signal was detected for
- `detected_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()
- `dot_number` TEXT NOT NULL — always present; resolved from docket when needed
- `docket_number` TEXT — present for authority/insurance signals
- `entity_key` TEXT NOT NULL — dedup key, format varies by signal type (see above)
- `severity` TEXT NOT NULL DEFAULT 'info' — one of: info, warning, critical
- `legal_name` TEXT — enriched from census
- `physical_state` TEXT — enriched from census
- `power_unit_count` INTEGER — enriched from census
- `driver_total` INTEGER — enriched from census
- `before_values` JSONB — previous state (null for "new" signals)
- `after_values` JSONB — current state (null for "disappeared" signals)
- `signal_details` JSONB — additional context (e.g., which BASICs worsened)
- `source_table` TEXT NOT NULL — the source table name
- `source_feed_name` TEXT NOT NULL — the feed that produced this signal
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()

**Constraints:**
- `UNIQUE(signal_type, feed_date, entity_key)` — idempotency

**Indexes:**
- `(signal_type, feed_date DESC)` — query by signal type + date range
- `(dot_number)` — carrier-level lookup
- `(feed_date DESC)` — "what happened today" queries
- `(severity)` — filter by severity
- `(physical_state, feed_date DESC)` — state-level dashboard queries

**RLS:** Enable row level security (follow existing FMCSA table pattern).
**Updated-at trigger:** Not needed — signals are insert-only, never updated.

Commit standalone.

---

## Deliverable 2: Signal Detection Service

Create `app/services/fmcsa_signal_detection.py`.

This is the core detection engine. Follow the connection pool pattern from `app/services/fmcsa_carrier_query.py` (`_get_pool()` with lazy init, `psycopg` with `dict_row`).

**Structure:**

1. **One detection function per signal type** — 9 functions, each returning a list of signal dicts ready for insertion. Each function takes `feed_date` (the target date to detect signals for) and the connection pool. Each function handles its own snapshot comparison logic (Pattern A or Pattern B as described above).

2. **Carrier enrichment helper** — a function that takes a list of `dot_number` values and returns a dict mapping `dot_number → {legal_name, physical_state, power_unit_count, driver_total}` from the latest census snapshot. Called after each detection function to enrich the signals. Batch the lookup (IN clause) for efficiency.

3. **Docket-to-DOT resolver** — a function that takes a list of `docket_number` values and returns a dict mapping `docket_number → dot_number` from `carrier_registrations` (latest snapshot, `usdot_number`). Used by insurance and authority signals.

4. **Detection orchestrator** — `run_signal_detection(feed_date: str) -> dict` — calls all 9 detection functions, enriches each signal batch with carrier context, persists all signals to `fmcsa_carrier_signals` using `INSERT ... ON CONFLICT(signal_type, feed_date, entity_key) DO NOTHING`, and returns a summary dict with counts per signal type and total.

**Important implementation notes:**
- All queries target the `entities` schema explicitly (e.g., `entities.motor_carrier_census_records`).
- For Pattern A diff queries: identify the two most recent `feed_date` values with `SELECT DISTINCT feed_date FROM entities.<table> ORDER BY feed_date DESC LIMIT 2`. Then compare.
- For Pattern B diff queries: identify the two most recent distinct `source_observed_at` values with `SELECT DISTINCT source_observed_at FROM entities.<table> ORDER BY source_observed_at DESC LIMIT 2`. Then compare using `first_observed_at` / `last_observed_at`.
- The `safety_worsened` detection must compare percentile values per carrier between two snapshots. Use `DISTINCT ON (dot_number)` within each snapshot CTE to get one row per carrier per snapshot, then join on `dot_number`. Only emit a signal when a percentile crosses a threshold (75 or 90), not for any increase.
- Persistence: use a single `INSERT ... VALUES ... ON CONFLICT DO NOTHING` per batch. The `executemany` pattern or a single multi-row insert are both acceptable.
- If a source table has no data for two distinct snapshots (e.g., only one feed_date exists), skip that signal type gracefully and return an empty list.

Commit standalone.

---

## Deliverable 3: Internal Detection Endpoint

Add to `app/routers/internal.py`:

**Endpoint:** `POST /fmcsa-signals/detect`

**Auth:** `require_internal_key` (same as all internal endpoints).

**Request model:** `InternalDetectFmcsaSignalsRequest` with one required field: `feed_date: str` (ISO date, e.g., `"2026-03-17"`).

**Handler:** Calls `run_signal_detection(feed_date=payload.feed_date)` from the detection service. Returns `DataEnvelope(data=result)` where `result` is the summary dict from the orchestrator.

**Import strategy:** Lazy import of `run_signal_detection` inside the handler (same pattern as other lazy imports in internal.py) to avoid adding to the module-level import block.

Commit standalone.

---

## Deliverable 4: Trigger.dev Scheduled Task

Create `trigger/src/tasks/fmcsa-signal-detection.ts`.

**Task:** A scheduled Trigger.dev task that runs daily and calls the detection endpoint.

**Schedule:** Daily at 5:00 PM ET (17:00 America/New_York). This runs well after the FMCSA ingestion window (typically 10 AM - 2 PM ET).

**Logic:**
1. Resolve the internal API config using `resolveInternalApiConfig()` from `trigger/src/workflows/internal-api.ts`.
2. Create an `InternalApiClient` using `createInternalApiClient`.
3. Determine today's feed date (UTC date string, YYYY-MM-DD).
4. Call `POST /api/internal/fmcsa-signals/detect` with `{ feed_date: "<today>" }`.
5. Log the response summary (signal counts per type).

**Error handling:** If the endpoint returns a non-200 status, log the error and let the task fail (Trigger.dev will show the failure in the dashboard). Do not retry automatically — if ingestion was incomplete, re-running would produce incomplete signals.

**Task ID:** `fmcsa-signal-detection`

Follow existing Trigger.dev task patterns in the repo for imports, task definition, and logging.

Commit standalone.

---

## Deliverable 5: Tests

Create `tests/test_fmcsa_signal_detection.py`.

All tests mock database calls. Use `pytest`. Do not hit real databases.

**1. Detection function tests (one per signal type):**
- `new_carrier`: given two snapshots where snapshot B has DOT numbers not in snapshot A, returns correct signals with `signal_type="new_carrier"`, correct `entity_key`, and enriched census fields.
- `disappeared_carrier`: given two snapshots where snapshot A has DOT numbers not in snapshot B, returns correct signals.
- `authority_granted`: given new fingerprint-based records with grant action descriptions, returns correct signals with resolved `dot_number`.
- `authority_revoked`: given new revocation records, returns correct signals.
- `insurance_added`: given new non-removal insurance records, returns correct signals with docket→DOT resolution.
- `insurance_lapsed`: given removal signal records and disappeared records, returns correct signals.
- `safety_worsened`: given two snapshots where carrier X had percentile 70 → 80 (crossed 75), emits signal. Carrier Y had 74 → 74 (no cross), no signal. Carrier Z had 89 → 91 (crossed 90), emits critical signal.
- `new_crash`: given crashes in today's snapshot not in yesterday's, returns correct signals with severity based on fatalities.
- `new_oos_order`: given new OOS orders, returns correct signals.

**2. Enrichment tests:**
- Carrier enrichment helper returns correct census fields for known DOT numbers, None for unknown.
- Docket-to-DOT resolver returns correct mappings, skips unknown dockets.

**3. Orchestrator tests:**
- `run_signal_detection` calls all 9 detection functions and returns a summary with correct counts.
- Idempotency: calling twice with the same feed_date produces the same summary (ON CONFLICT DO NOTHING means second run inserts 0 new rows).
- Graceful skip: if a table has only one snapshot (not two), that signal type returns 0 signals and no error.

**4. Endpoint test:**
- `POST /api/internal/fmcsa-signals/detect` with valid auth and feed_date returns 200 with DataEnvelope containing the summary.
- Missing auth returns 401.

Commit standalone.

---

## What is NOT in scope

- **No query endpoints for consuming signals.** That is a separate directive.
- **No changes to existing FMCSA tables or services.** The detection engine reads from them but does not modify them.
- **No changes to the FMCSA ingestion pipeline.** The detection engine is downstream of ingestion.
- **No changes to `app/main.py`.**
- **No deploy commands.** Do not push. Do not deploy Trigger.dev.
- **No Railway configuration changes.**
- **No changes to `app/routers/fmcsa_v1.py`.** Signal query endpoints are a separate directive.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Schema: table name, column count, unique constraint, index count
(b) Detection service: function count (should be 9 + enrichment helper + docket resolver + orchestrator = 12+), connection pool config
(c) Detection logic: confirm which tables use Pattern A (feed_date) vs Pattern B (fingerprint), and how the detection window is determined for each
(d) Internal endpoint: path, request model, auth approach
(e) Trigger.dev task: task ID, schedule (cron expression), feed_date determination logic
(f) Tests: total test count, all passing, confirm all 9 signal types have dedicated test coverage
(g) Anything to flag — especially: any table that lacks sufficient data for two-snapshot comparison in production, any concern about query performance on large tables, any ambiguity in the signal type definitions that required a judgment call
