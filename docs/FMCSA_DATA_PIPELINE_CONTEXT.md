# FMCSA Data Pipeline Context

## Purpose
The FMCSA data pipeline is a bulk-ingestion and lookup layer for U.S. Federal Motor Carrier Safety Administration open data. FMCSA publishes public records about motor carriers, brokers, freight forwarders, operating authority, insurance filings, revocations, safety scores, inspections, crashes, out-of-service orders, and carrier census data.

For the business, this matters because trucking factoring companies and insurance brokers need early, high-signal visibility into carrier changes. New authority filings, insurance changes, revoked authority, new census records, deteriorating safety scores, crash activity, inspection volume, and out-of-service events can all indicate new sales opportunities, underwriting risk, churn risk, or account-management triggers.

The pipeline is intentionally designed as source-observation storage first, not opinionated business logic. It captures daily FMCSA snapshots faithfully so a later signal-detection layer can answer questions like:

- Which carriers appeared for the first time today?
- Which carriers lost insurance coverage or changed filing status?
- Which carriers were newly revoked, newly out-of-service, or newly crash-active?
- Which carriers had safety or inspection metrics materially worsen?

## Core Design
The FMCSA layer follows a few hard rules:

- FMCSA data is global public data, not tenant-scoped enrichment output.
- Canonical storage is organized by business concept, not by provider or pipeline step.
- Every observed row is stored with a `feed_date`.
- Ingestion does not deduplicate business rows across days.
- Same-day reruns are idempotent at `(feed_date, source_feed_name, row_position)`.
- Different `feed_date` values coexist as separate snapshots, even if the business row looks identical.
- Raw source data is preserved in `raw_source_row` JSONB.
- Source metadata is preserved alongside typed business columns.
- The ingestion layer is intentionally dumb; a separate diff/signal process is expected to compare snapshots later.

This means the FMCSA layer is not trying to produce one current master record per carrier. It is trying to produce a trustworthy daily observation ledger.

## Storage Model
Each canonical FMCSA table stores typed business columns plus shared metadata and lineage fields. The important semantics are:

- `feed_date` identifies the observed daily snapshot date.
- `row_position` preserves source-row identity within that day’s file.
- `source_feed_name` distinguishes feeds that share the same table.
- `source_file_variant` distinguishes daily snapshot, all-with-history, daily-diff, and CSV-export artifacts.
- `raw_source_row` preserves the original source row as JSONB, including ordered values, keyed fields, and source row number.
- `source_run_metadata` preserves schedule/run metadata for the ingest invocation.
- `created_at` and `updated_at` track storage lifecycle.

For the five history-style tables that predate the broader 31-feed rollout, the system also preserves:

- `record_fingerprint` as a deterministic source-slot identity fallback for legacy schemas
- `first_observed_at` as insert-only
- `last_observed_at` as the latest observation time

The primary idempotency model is now `(feed_date, source_feed_name, row_position)`, but the write path still supports a legacy `record_fingerprint` fallback where live schema drift requires it.

## Feed Catalog
The FMCSA pipeline currently covers 31 scheduled feeds. They fall into four logical families.

### 1. Top 5 daily-diff feeds
These arrive as direct HTTP GET downloads of quoted comma-delimited headerless text files. Even though FMCSA labels them as daily-diff datasets, this pipeline stores them as observed daily snapshots.

| Feed | What it contains | Variant | Download method | Canonical table |
|---|---|---|---|---|
| `AuthHist` | Operating-authority lifecycle history rows for a docket and authority combination. It captures original and final authority actions rather than a flattened current authority state. | Daily snapshot from daily-diff file | Direct HTTP GET of headerless `.txt` file | `entities.operating_authority_histories` |
| `Revocation` | Operating-authority revocation events, including registration type, serve date, revocation type, and effective date. It is event/history data, not a current revocation flag table. | Daily snapshot from daily-diff file | Direct HTTP GET of headerless `.txt` file | `entities.operating_authority_revocations` |
| `Insurance` | Insurance policy inventory rows for carrier dockets, including type, policy number, effective date, and insurer. The daily feed also emits blank/zeroed removal rows that are preserved as removal signals instead of discarded. | Daily snapshot from daily-diff file | Direct HTTP GET of headerless `.txt` file | `entities.insurance_policies` |
| `ActPendInsur` | Active and pending insurance filing rows with posting, effective, and cancel-effective timing fields. This is filing-state data, not the same concept as the simpler policy inventory table. | Daily snapshot from daily-diff file | Direct HTTP GET of headerless `.txt` file | `entities.insurance_policy_filings` |
| `InsHist` | Historical outgoing policy events such as cancellations, replacements, transfers, and related filing changes. It describes prior policy history, not the replacement/current policy. | Daily snapshot from daily-diff file | Direct HTTP GET of headerless `.txt` file | `entities.insurance_policy_history_events` |

### 2. Snapshot/history expansion feeds
These are also FMCSA bulk feeds, mostly sourced as direct HTTP GET headerless text files. Some are daily-snapshot feeds and some are all-with-history variants. Several share tables with their daily counterparts because the underlying business concept is the same.

| Feed | What it contains | Variant | Download method | Canonical table |
|---|---|---|---|---|
| `Carrier` | Broad carrier registration and authority snapshot rows, including legal/DBA identity, address blocks, authority status, revocation flags, and insurance-on-file summary fields. It functions as the broad carrier census/registration view for the daily artifact. | Daily snapshot | Direct HTTP GET of headerless `.txt` file | `entities.carrier_registrations` |
| `Rejected` | Rejected insurance filing rows, including policy, dates, rejection reason, insurer, and coverage amounts. These are compliance/enforcement rows distinct from active policies or policy history. | Daily snapshot | Direct HTTP GET of headerless `.txt` file | `entities.insurance_filing_rejections` |
| `BOC3` | Process-agent filing rows showing the registered process agent and address details tied to a docket or USDOT number. It is a legal filing concept, not a carrier master or insurance concept. | Daily snapshot | Direct HTTP GET of headerless `.txt` file | `entities.process_agent_filings` |
| `InsHist - All With History` | Full all-history version of outgoing insurance policy history events. It shares the same row concept as daily `InsHist`, so it lands in the same canonical history table with provenance preserved in metadata. | All-with-history snapshot | Direct HTTP GET of headerless `.txt` file | `entities.insurance_policy_history_events` |
| `BOC3 - All With History` | Full all-history version of process-agent filings. It shares the same business concept as daily `BOC3`, so both variants land in the same process-agent table. | All-with-history snapshot | Direct HTTP GET of headerless `.txt` file | `entities.process_agent_filings` |
| `ActPendInsur - All With History` | Full all-history version of active and pending insurance filing rows. It shares table storage with daily `ActPendInsur` because the row concept is the same. | All-with-history snapshot | Direct HTTP GET of headerless `.txt` file | `entities.insurance_policy_filings` |
| `Rejected - All With History` | Full all-history version of rejected insurance filing rows. It shares the same rejection concept and table as daily `Rejected`. | All-with-history snapshot | Direct HTTP GET of headerless `.txt` file | `entities.insurance_filing_rejections` |
| `AuthHist - All With History` | Full all-history version of authority lifecycle history. It shares table storage with daily `AuthHist` because the row meaning is the same authority-history concept. | All-with-history snapshot | Direct HTTP GET of headerless `.txt` file | `entities.operating_authority_histories` |

### 3. SMS feeds
These use the Socrata CSV export endpoint and arrive as headered CSV files. They represent Safety Measurement System summaries and source inputs. One originally considered feed, `SMS Input - Crash`, was explicitly removed from scope and is not part of the 31 scheduled tasks.

| Feed | What it contains | Variant | Download method | Canonical table |
|---|---|---|---|---|
| `SMS AB PassProperty` | BASIC summary measures for the AB carrier segment without percentile or roadside-alert fields. It stores counts, measures, and acute/critical indicators for the major BASIC categories. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_safety_basic_measures` |
| `SMS C PassProperty` | BASIC summary measures for the C carrier segment without percentile or roadside-alert fields. It shares the same concept and table as `SMS AB PassProperty`, differentiated by carrier segment and source metadata. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_safety_basic_measures` |
| `SMS Input - Violation` | Row-level inspection violations contributing to SMS calculations, including violation code, BASIC category, OOS and severity weights, and section/group descriptions. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_inspection_violations` |
| `SMS Input - Inspection` | Row-level inspections contributing to SMS calculations, including inspection identifiers, timing, OOS counts, hazmat counts, unit identifiers, and BASIC relevance flags. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_inspections` |
| `SMS Input - Motor Carrier Census` | Carrier census and registration source rows used by SMS, including legal/DBA names, addresses, contact info, mileage, operation flags, and fleet metadata. | Daily snapshot | CSV export endpoint with header row | `entities.motor_carrier_census_records` |
| `SMS AB Pass` | BASIC summary measures for the AB segment with percentile and alert fields added on top of the underlying measures. This is materially different from PassProperty and therefore uses a separate table. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_safety_basic_percentiles` |
| `SMS C Pass` | BASIC summary measures for the C segment with percentile and alert fields. It shares the same concept and table as `SMS AB Pass`, separated by carrier segment and metadata. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_safety_basic_percentiles` |

### 4. Remaining CSV export feeds
These also use the Socrata CSV export endpoint with header rows. They expand the FMCSA coverage to crashes, deeper census exports, inspection sub-rows, out-of-service data, and all-history CSV datasets.

| Feed | What it contains | Variant | Download method | Canonical table |
|---|---|---|---|---|
| `Crash File` | Commercial motor vehicle crash rows with timing, location, severity, vehicle configuration, and attached carrier-identification fields. It is crash-level source history, not a deduplicated carrier event summary. | Daily snapshot | CSV export endpoint with header row | `entities.commercial_vehicle_crashes` |
| `Carrier - All With History` | Full all-history carrier registration and authority rows. It shares the `carrier_registrations` table with daily `Carrier` because the concept is the same. | All-with-history snapshot | CSV export endpoint with header row | `entities.carrier_registrations` |
| `Inspections Per Unit` | Vehicle-unit child rows attached to inspections, including unit identifiers, make, company/unit number, license, VIN, and decal information. | Daily snapshot | CSV export endpoint with header row | `entities.vehicle_inspection_units` |
| `Special Studies` | Special-study child rows attached to inspections. It captures study identifiers and sequence details for inspection-linked studies. | Daily snapshot | CSV export endpoint with header row | `entities.vehicle_inspection_special_studies` |
| `Revocation - All With History` | Full all-history operating-authority revocation rows. It shares storage with daily `Revocation` because the business concept and row semantics match. | All-with-history snapshot | CSV export endpoint with header row | `entities.operating_authority_revocations` |
| `Insur - All With History` | Full all-history insurance policy inventory rows. It shares storage with daily `Insurance`, while retaining daily removal-signal behavior only for the daily-diff feed. | All-with-history snapshot | CSV export endpoint with header row | `entities.insurance_policies` |
| `OUT OF SERVICE ORDERS` | FMCSA out-of-service order rows, including order date, reason, status, and rescind date. It is a separate enforcement concept rather than part of carrier registration or safety score tables. | Daily snapshot | CSV export endpoint with header row | `entities.out_of_service_orders` |
| `Inspections and Citations` | Citation outcome child rows attached to inspections and violations. It stores citation codes and results rather than inspection headers or violation bodies. | Daily snapshot | CSV export endpoint with header row | `entities.vehicle_inspection_citations` |
| `Vehicle Inspections and Violations` | MCMIS-style inspection violation rows with inspection identifiers, part/section codes, category fields, OOS indicator, defect verification, and citation references. It shares the same canonical table as `SMS Input - Violation` because both are inspection-violation observations. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_inspection_violations` |
| `Company Census File` | The widest carrier census export, with 147 columns covering identity, status, organization, officers, mileage, cargo flags, equipment counts, safety-rating fields, and docket-status fields. It is the richest source for carrier census/registration attributes. | Daily snapshot | CSV export endpoint with header row | `entities.motor_carrier_census_records` |
| `Vehicle Inspection File` | Rich inspection-header rows with lifecycle timestamps, service-center and facility metadata, enforcement/search metadata, violation counts, upload metadata, and carrier address fields. It is the broad inspection-header complement to the smaller SMS inspection feed. | Daily snapshot | CSV export endpoint with header row | `entities.carrier_inspections` |

## Write Path Evolution
The FMCSA write path has gone through three generations.

### Generation 1: Supabase PostgREST client
The first version wrote through the Supabase HTTP/PostgREST layer. That approach worked functionally but was a bad fit for high-volume FMCSA ingest because every batch write paid extra HTTP overhead and amplified concurrent load against both the app layer and database. Under heavier concurrency it produced slowdowns and 502-style failures.

### Generation 2: direct Postgres via `psycopg` `executemany`
The second version moved to direct PostgreSQL connections from FastAPI and replaced the HTTP write path with parameterized `INSERT ... ON CONFLICT DO UPDATE` statements executed with `psycopg` `executemany`. This was materially better than PostgREST because it removed a large amount of HTTP overhead and kept failures loud.

But it was still fundamentally row-oriented:

- each row was adapted independently
- each row paid JSONB serialization costs independently
- each row hit conflict detection independently
- each row evaluated update logic independently

That was acceptable for small and moderate feeds, but not for the largest datasets. Large feeds could still take one to two hours or more, which made timeouts and infrastructure pressure much more likely.

### Generation 3: COPY-based bulk writes
The current/deploying generation replaces row-oriented upserts with a true bulk-write pattern:

1. Build the same typed row dictionaries as before.
2. Create a temporary staging table.
3. Bulk load the batch into staging with PostgreSQL `COPY FROM STDIN`.
4. Run one set-based `INSERT ... SELECT ... ON CONFLICT DO UPDATE` merge into the canonical table.

This keeps the external contracts and row semantics the same while changing only the write mechanism. The expected gain is roughly 10x to 50x versus the `executemany` path, especially on wide or very large feeds.

COPY-era batching moves toward much larger write sizes:

- baseline default: 5,000 rows per write batch
- largest feeds: 10,000 rows per write batch
- the two explicit 10,000-row feeds are `Company Census File` and `Vehicle Inspection File`

## COPY Implementation Details
The COPY design is important because it preserves FMCSA semantics while radically changing throughput.

### Staging table strategy
For each write call, FastAPI opens one direct Postgres connection and one transaction, then creates a unique temporary staging table using the equivalent of:

- `CREATE TEMP TABLE ... LIKE target_table INCLUDING DEFAULTS ON COMMIT DROP`

This keeps the staging table aligned with the live target table’s types and defaults without hand-maintaining a second schema definition.

### COPY format
The bulk loader uses PostgreSQL text COPY, not binary COPY and not CSV COPY. The format choices are deliberate:

- UTF-8 encoding
- tab-delimited fields
- newline row delimiter
- `\N` for SQL `NULL`
- empty field for empty string
- compact JSON text for JSONB fields

That format preserves the difference between missing values and blank strings, which matters for FMCSA data, and it safely handles wide rows plus raw JSON payloads.

### Merge pattern
After staging, the system runs one set-based merge:

- insert from staging into the real canonical table
- conflict target is primarily `(feed_date, source_feed_name, row_position)`
- if the live schema does not support that key yet, fall back to `record_fingerprint`
- on conflict, update all mutable business and metadata columns

### Conflict-key semantics
The source-slot identity model is:

- same `feed_date`
- same `source_feed_name`
- same `row_position`

That means rerunning the same feed on the same day updates that same source slot. But the same business row observed on a later `feed_date` becomes a separate stored snapshot.

### Insert-only versus mutable fields
These fields are insert-only and must never change on conflict:

- `created_at`
- `record_fingerprint`
- `first_observed_at`

These fields update on conflict:

- `updated_at`
- `last_observed_at` for the five history-style tables
- all mutable typed business columns
- raw and source metadata columns

### Error handling
The COPY path is designed to fail loudly:

- temp-table creation failure aborts immediately
- COPY failure rolls back the transaction
- merge failure rolls back the transaction
- commit failure is surfaced as a failure

Cleanup uses both transaction semantics and explicit best-effort temp-table drop logic. The design goal is simple: no silent success, no partial commit, no “pipeline completed but rows did not land” ambiguity inside this write layer.

## Trigger.dev Orchestration And Scheduling
The FMCSA ingest is orchestrated by Trigger.dev, with one scheduled task per feed and one shared workflow implementation behind them.

The important operational facts are:

- there are 31 scheduled tasks
- each feed has its own task file
- all tasks run in `America/New_York`
- they are staggered exactly 7 minutes apart
- the first task starts at 10:05 AM ET
- the last task starts at 1:35 PM ET

The schedule order is:

1. Top 5 daily-diff feeds
2. Snapshot/history expansion feeds
3. SMS feeds
4. Remaining CSV export feeds

The shared workflow handles two source shapes:

- headerless quoted comma-delimited text files
- headered CSV export files

It validates headers where applicable, validates row width against the locked contract, and normalizes each row into a shared FMCSA payload shape before persistence.

### Streaming ingestion
Large feeds no longer rely on fully buffering the file in memory before parsing. Streaming parse and chunked persistence are used for the heavier feeds, especially:

- large all-history plain-text feeds that previously hit OOM conditions
- `Company Census File`
- `Vehicle Inspection File`

This is a major part of the memory-safety story. The earlier OOM failures on large all-history feeds were operational evidence that a buffered approach was unsafe at production scale.

### Timeout and machine-size tuning
The task fleet includes feed-specific runtime tuning:

- most FMCSA tasks use long max-duration settings
- the heaviest plain-text all-history feeds were moved onto larger machines
- several larger CSV-export feeds use `medium-2x`
- some moderate inspection child feeds use `small-2x`
- `Company Census File` and `Vehicle Inspection File` have dedicated machine overrides and shorter explicit task max-duration settings than the rest of the FMCSA fleet

The strategic takeaway is that FMCSA ingest is not one homogeneous workload. Some feeds are tiny and cheap; some are wide, large, or memory-sensitive enough to require explicit runtime tuning.

## Socrata Per-Carrier Query Layer
Separate from the bulk-ingestion pipeline, the system also has an on-demand Socrata per-carrier lookup layer. This is not for full-dataset ingest. It is for targeted enrichment of one carrier at a time by DOT number or MC number.

The provider model is:

- Socrata SODA3 query API
- HTTP Basic auth using Socrata API credentials
- dataset-specific exact-match SoQL queries
- thin wrapper operations rather than a generic public “query any dataset” surface

The four implemented operations are:

| Operation | Purpose | Identifier support |
|---|---|---|
| `company.enrich.fmcsa.company_census` | Look up a single carrier in the Company Census File. | DOT or MC |
| `company.enrich.fmcsa.carrier_all_history` | Look up a single carrier in Carrier - All With History. | DOT or MC |
| `company.enrich.fmcsa.revocation_all_history` | Look up a single carrier in Revocation - All With History. | DOT or MC |
| `company.enrich.fmcsa.insur_all_history` | Look up a single carrier in Insur - All With History. | MC only |

This layer is complementary to the bulk feeds:

- bulk ingest gives full-dataset daily snapshots
- per-carrier Socrata queries give targeted, on-demand lookups for one carrier when a workflow or user specifically needs it

The per-carrier layer is useful when you do not want to wait for downstream diff logic or when a workflow needs an immediate lookup for a known DOT or MC number.

## What Is Not Yet Built
Several strategically important pieces are still missing.

### Diff and signal detection
The biggest missing layer is the actual comparison engine that looks at today’s snapshot versus prior snapshots and emits business signals:

- new carriers
- removed carriers
- changed authority status
- new insurance filings
- removed insurance
- new revocations
- new out-of-service orders
- changing safety posture

That diff/signals layer is the business payoff, but it is intentionally downstream from ingestion and has not been built yet.

### Snapshot retention cleanup
The current storage model preserves daily snapshots indefinitely unless something later cleans them up. A retention policy and cleanup process for snapshots older than a chosen number of days has not been built yet.

### Raw file archival
The pipeline preserves raw rows in JSONB, but it does not yet archive the original downloaded source files to object storage.

### Remaining Socrata per-carrier wrappers
Only 4 targeted Socrata wrapper operations are implemented so far. The remaining planned set, described as 15 additional per-carrier query operations, is still unbuilt.

## Current Production Status
The FMCSA workstream is mid-rollout rather than fully settled.

The current picture is:

- the production database is being upgraded from Micro (1 GB) to Large (8 GB) with 100 GB of disk
- the COPY write path is committed in code but not yet deployed
- deployment of the COPY path is expected after the database upgrade completes
- 15 of the 31 feeds have been confirmed working at least once on the direct-Postgres `executemany` path
- several feeds still need explicit validation on the COPY path

The main production problems so far have been:

- concurrent write load overwhelming the database and/or FastAPI during heavy ingest windows
- timeout configuration existing at multiple layers and not always matching deployed reality
- OOM on large all-history feeds before streaming parsing was introduced
- column mismatches between live table schemas and the write-path expectations, fixed iteratively by runtime column intersection and schema adjustments

This means the FMCSA initiative is past the “design only” stage but not yet at “boringly reliable at full scale.” The main remaining work is operational hardening plus the downstream signal layer.

## Canonical Table Inventory
The canonical FMCSA table inventory in the `entities` schema is:

| Table | What it stores | Feeds writing to it |
|---|---|---|
| `operating_authority_histories` | Authority lifecycle history rows. | `AuthHist`, `AuthHist - All With History` |
| `operating_authority_revocations` | Operating-authority revocation rows. | `Revocation`, `Revocation - All With History` |
| `insurance_policies` | Insurance policy inventory rows plus daily removal signals. | `Insurance`, `Insur - All With History` |
| `insurance_policy_filings` | Active/pending insurance filing rows with timing fields. | `ActPendInsur`, `ActPendInsur - All With History` |
| `insurance_policy_history_events` | Outgoing policy history and cancellation/replacement events. | `InsHist`, `InsHist - All With History` |
| `carrier_registrations` | Broad carrier registration, authority, identity, and address snapshots. | `Carrier`, `Carrier - All With History` |
| `process_agent_filings` | BOC3 process-agent filing rows. | `BOC3`, `BOC3 - All With History` |
| `insurance_filing_rejections` | Rejected insurance filing rows. | `Rejected`, `Rejected - All With History` |
| `carrier_safety_basic_measures` | BASIC measure summaries without percentile/alert fields. | `SMS AB PassProperty`, `SMS C PassProperty` |
| `carrier_safety_basic_percentiles` | BASIC summaries with percentile and alert fields. | `SMS AB Pass`, `SMS C Pass` |
| `carrier_inspection_violations` | Inspection-violation source rows. | `SMS Input - Violation`, `Vehicle Inspections and Violations` |
| `carrier_inspections` | Inspection header/source rows. | `SMS Input - Inspection`, `Vehicle Inspection File` |
| `motor_carrier_census_records` | Carrier census and registration source rows. | `SMS Input - Motor Carrier Census`, `Company Census File` |
| `commercial_vehicle_crashes` | Crash-level FMCSA source rows. | `Crash File` |
| `vehicle_inspection_units` | Inspection-linked vehicle unit child rows. | `Inspections Per Unit` |
| `vehicle_inspection_special_studies` | Inspection-linked special-study child rows. | `Special Studies` |
| `out_of_service_orders` | FMCSA out-of-service order rows. | `OUT OF SERVICE ORDERS` |
| `vehicle_inspection_citations` | Inspection-linked citation result rows. | `Inspections and Citations` |

## Strategic Takeaways
If a future AI agent is making architectural decisions around this workstream, the most important truths are:

- The FMCSA layer is a daily source-observation system, not yet a signal engine.
- Snapshot fidelity is intentionally favored over early deduplication or inference.
- Shared-table storage is used only when feeds truly represent the same business concept.
- COPY-based bulk writes are the key enabling change for full-scale FMCSA ingest.
- Operational tuning matters because the 31 feeds vary enormously in width, volume, and runtime profile.
- The business value will come from the not-yet-built diff and signal layer on top of this snapshot foundation.
