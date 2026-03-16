# SAM.gov Public Entity Extract — Ingestion Report

**Date:** 2026-03-16

---

## What Was Built

A complete ingestion pipeline for SAM.gov Public V2 entity registration extracts — from raw `.dat` file parsing to bulk persistence in Supabase.

### Components

| Component | File | Purpose |
|---|---|---|
| Column map | `app/services/sam_gov_column_map.py` | 142 Public V2 column definitions (positions, names, snake_case mappings) generated from `SAM_MASTER_EXTRACT_MAPPING_Feb2025.json` |
| Migration | `supabase/migrations/030_sam_gov_entities.sql` | `entities.sam_gov_entities` table — 142 SAM TEXT columns + 12 metadata columns, 6 indexes, RLS enabled |
| Bulk persistence | `app/services/sam_gov_common.py` | Line parser, row builder, COPY-based bulk upsert with dedicated connection pool |
| Ingest service | `app/services/sam_gov_extract_ingest.py` | Top-level orchestrator — reads `.dat`, skips BOF header, parses lines, persists in 50K-row chunks |
| Download service | `app/services/sam_gov_extract_download.py` | SAM.gov Extracts API client — fetches ZIP, extracts `.dat` |
| Internal endpoint | `app/routers/internal.py` | `POST /api/internal/sam-gov-entities/ingest` with `require_internal_key` auth |
| Config | `app/config.py` | `SAM_GOV_API_KEY` env var (Doppler) |
| Tests | `tests/test_sam_gov_ingest.py` | 24 tests — column map, parser, row builder, ingest service |

### Scripts (one-off, not production code)

| Script | Purpose |
|---|---|
| `scripts/validate_sam_gov_field_count.py` | API-based field count validation (used during development) |
| `scripts/validate_sam_gov_parse.py` | Parse validation against real downloaded file (100 rows) |
| `scripts/run_sam_gov_full_ingest.py` | Full monthly ingest runner |

---

## Data Source: SAM.gov Public V2 Extract

| Property | Value |
|---|---|
| Source | SAM.gov (System for Award Management) — US federal entity registration database |
| File format | Pipe-delimited `.dat` flat file in `.ZIP` |
| Encoding | UTF-8 |
| Fields per record | **142** (Public V2 format — FOUO/Sensitive columns omitted) |
| Header row | None — first line is BOF metadata, data starts on line 2 |
| End of record | `!end` marker in field 142 |
| Primary key | UEI (Unique Entity Identifier) — 12-char alphanumeric |
| Monthly full dump | ~875K records, ~530MB uncompressed |
| Daily delta | Thousands of records (new/updated/deleted/expired) |
| API | `GET https://api.sam.gov/data-services/v1/extracts` — rate limited to 50 requests/day |

### Key fields ingested

- **Identity:** UEI, Legal Business Name, DBA Name, CAGE Code
- **Address:** Physical address (line1, line2, city, state, zip, country, congressional district), mailing address
- **Industry:** Primary NAICS, all NAICS codes (tilde-separated with small business flags), PSC codes
- **Entity structure:** Entity structure code, state/country of incorporation, business type codes
- **Registration:** Registration dates (initial, expiration, last update, activation), SAM Extract Code (A/E/1-4)
- **Points of contact:** 6 POC slots (Govt Business, Alt Govt Business, Past Performance, Alt Past Performance, Electronic Business, Alt Electronic Business) — names, titles, addresses only (email/phone are FOUO)
- **SBA certifications:** Business type codes with descriptions and entry/exit dates
- **Other:** Entity URL, exclusion status, debt offset flag, disaster response data, EVS source

---

## Table Design

**Table:** `entities.sam_gov_entities`

**Composite unique key:** `(extract_date, unique_entity_id)` — supports loading multiple monthly snapshots side by side and daily delta upserts.

**Extract metadata on every record:**

| Column | Purpose |
|---|---|
| `extract_date` | Which monthly/daily file this came from (e.g., `2026-03-01`) |
| `extract_type` | `MONTHLY` or `DAILY` |
| `extract_code` | SAM Extract Code — A/E for monthly, 1/2/3/4 for daily |
| `source_filename` | Original `.dat` filename (e.g., `SAM_PUBLIC_MONTHLY_V2_20260301.dat`) |
| `source_download_url` | URL the ZIP was downloaded from |
| `ingested_at` | Timestamp when the row was written |
| `row_position` | 1-based row number in the source file |
| `raw_source_row` | Original pipe-delimited line preserved verbatim |

**Indexes:** UEI, extract_date DESC, extract_code, primary_naics, state, legal_business_name (text_pattern_ops).

This design enables:
- Loading March, April, May side by side
- Diffing between months (new registrations, changes, expirations)
- Loading historical archives (SAM has monthly files back to 2022)
- Tracing any record to its exact source file and line number
- Idempotent reprocessing of any file

---

## First Ingest Results

**File:** `SAM_PUBLIC_MONTHLY_V2_20260301.dat` (March 2026 monthly full dump)

| Metric | Value |
|---|---|
| Total rows parsed | 874,710 |
| Rows accepted | 874,709 |
| Rows rejected | 1 (EOF trailer line) |
| Rows written | 867,137 |
| Duplicate UEIs deduplicated | 7,572 (last occurrence wins) |
| Chunks | 18 (50K rows each) |
| Chunk time | ~20 seconds each |
| Total elapsed | 6 minutes 0.8 seconds |

---

## Key Discovery During Build

The original directive assumed 368 fields per record based on the SAM Master Extract Mapping JSON (which covers all sensitivity tiers). Validation against real downloaded files revealed the **Public V2 extract contains 142 fields** — only the columns marked `Public` in the mapping. FOUO and Sensitive columns are omitted entirely, not sent as empty fields. This was confirmed across 4 downloaded files (Feb and March 2026, both encoding variants).

The pipeline was rebuilt for 142 columns before the full ingest.

---

## What Is NOT Built Yet

- **No Trigger.dev scheduled task.** Ingestion is manual (script or internal endpoint). Automated monthly/daily cron is future work.
- **No query endpoint.** No `/api/v1/sam-gov-entities/query`. Separate directive.
- **No derived tables or views.** No materialized "current state" view, no NAICS parsing, no business type decoding.
- **No entity resolution.** SAM.gov data lives in its own dedicated table — not yet linked to `company_entities`.
- **No FOUO data.** Table has 142 Public columns only. FOUO access (email, phone, employee count, revenue, parent hierarchy) requires a Federal System Account.
- **No daily delta automation.** The pipeline supports daily deltas structurally, but no scheduled fetch.
- **No historical backfill.** Only March 2026 is loaded. SAM has monthly archives back to 2022.
