# Executor Report: Operational Reality Check Refresh

**Date:** 2026-03-18

---

## (a) New Report

- **Path:** `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`
- **Sections:** 8 (plus executive summary, changes since March 10, and bottom line)
- **SQL queries run:** ~30 distinct production queries
- **Failed queries / missing tables:**
  - `entities.mv_fmcsa_authority_grants` — does not exist (migration 036 not applied)
  - `entities.mv_fmcsa_insurance_cancellations` — does not exist (migration 037 not applied)
  - `usaspending_contracts MAX(created_at)` timed out on first attempt (14.6M rows), succeeded with extended timeout

## (b) Top 5 Key Deltas from March 10

1. **Schema split complete** — production moved from `public` to `ops` + `entities` schemas
2. **company_entities exploded**: `88` → `45,679` (+45,591) via Clay ingestion (`external.ingest.clay.find_companies`)
3. **FMCSA infrastructure live**: all 18 canonical tables populated with `75.8M` total rows, data current as of 2026-03-17
4. **Federal data tables new**: `sam_gov_entities` (867K), `sba_7a_loans` (356K), `usaspending_contracts` (14.7M), `mv_federal_contract_leads` MV (1.3M)
5. **All stuck runs resolved**: 8 stuck `running` pipeline_runs → `failed`, 7 `running` step_results → `failed`, 190 `queued` → `skipped`

## (c) CLAUDE.md Updates

- **Sections changed:** Documentation Authority (1 ref), Production State header + all subsections (What Works, What Is Broken, What Has Never Been Used), Diagnostic Reports (1 ref)
- **Filename references updated:** 3 occurrences of `OPERATIONAL_REALITY_CHECK_2026-03-10` → `2026-03-18`
- **Added:** `<!-- Last updated -->` timestamp at top

## (d) Cross-Reference Updates

| File | References changed |
|---|---:|
| `docs/WRITING_EXECUTOR_DIRECTIVES.md` | 2 |
| `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md` | 2 |
| `docs/DATA_ENGINE_X_ARCHITECTURE.md` | 2 (+ date in header) |
| `docs/STRATEGIC_DIRECTIVE.md` | 1 |
| `docs/CHIEF_AGENT_DIRECTIVE.md` | 4 (+ production reality description update) |

## (e) FMCSA Tables

- **18 of 18 canonical tables exist** in production
- **18 of 18 have data** (all populated)
- **Total FMCSA rows:** `75,823,609`
- **fmcsa_carrier_signals:** exists, 0 rows
- **mv_fmcsa_authority_grants:** does not exist (migration 036 not applied)
- **mv_fmcsa_insurance_cancellations:** does not exist (migration 037 not applied)

## (f) Flags

- **Clay ingestion is the dominant data path now** — 99.8% of company_entities are from `external.ingest.clay.find_companies`, not pipeline execution. These operations (`external.ingest.clay`, `external.ingest.clay.find_companies`, `external.ingest.clay.find_people`) are not in the execute_v1.py catalog and bypass pipeline orchestration entirely.
- **Two FMCSA materialized views missing** — migrations 036 and 037 are in the repo but not applied to production. Same class of problem as the old `company_ads` missing-table issue.
- **carrier_safety_basic_measures/percentiles lag 4 days behind** other FMCSA tables (2026-03-13 vs 2026-03-17). May indicate stalled SMS ingestion or a less frequent schedule.
- **No new pipeline activity since March 4** — all orchestration counts are unchanged. Production growth is entirely from external ingestion paths (Clay, FMCSA, federal data).
- **3 new tables discovered** not in March 10: `sam_gov_entities`, `sba_7a_loans`, `usaspending_contracts` — 17 new migrations (021–037) have been applied.
- **psql connection note**: `doppler run -- psql` without `"$DATABASE_URL"` connects to the local database, not production. All queries in the report used the explicit `psql "$DATABASE_URL"` pattern.
