# Directive: FMCSA Pipeline Performance Diagnosis and Recommendations

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA ingestion stack has already moved through multiple write-path generations and is now on a COPY-based bulk-write design in FastAPI. That solved one class of bottleneck, but the overall pipeline is still too slow. Medium feeds in the 2-6M row range are taking roughly 25-40+ minutes each. With 31 daily feeds staggered 7 minutes apart, that throughput is operationally unacceptable. The current end-to-end architecture is: Trigger.dev downloads and parses feed data, sends row batches as JSON over internal HTTP to FastAPI, FastAPI COPY-loads into a temp table, merges into canonical tables, returns confirmation, then Trigger sends the next batch. The likely remaining fundamental bottleneck is the per-batch HTTP round trip and the serialization/deserialization overhead around it. This directive is diagnosis and recommendation only. Do not implement changes yet.

**Current architecture under investigation:**

1. Trigger.dev downloads and parses one FMCSA feed
2. Trigger groups parsed rows into batches
3. Trigger serializes each batch to JSON
4. Trigger sends the batch over HTTP to a FastAPI internal endpoint
5. FastAPI deserializes the JSON request body
6. FastAPI COPY-loads rows into a temp table
7. FastAPI merges staging into the canonical `entities` table with one set-based upsert
8. FastAPI returns confirmation
9. Trigger sends the next batch

**Problem statement to evaluate:** For large and medium feeds, the per-batch HTTP round trip may now dominate wall time. At `5000-10000` rows per batch, a multi-million-row feed can still require hundreds of sequential HTTP requests. Even if database writes are efficient, total wall time may remain infeasible because serialization, transfer, request parsing, COPY, merge, and response confirmation all happen per batch.

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/fmcsa-daily-diff.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/internal-api.ts`
- `/Users/benjamincrane/data-engine-x-api/app/services/fmcsa_daily_diff_common.py`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_COPY_BULK_WRITE_PLAN.md`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_DATA_PIPELINE_CONTEXT.md`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/023_fmcsa_snapshot_history_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/024_fmcsa_sms_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/025_fmcsa_remaining_csv_export_tables.sql`

---

### Deliverable 1: Performance Diagnosis Report

Create `docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`.

This report must diagnose the current bottleneck and propose ranked recommendations. It must be evidence-driven, quantitative where possible, and explicit about what is measured versus inferred.

Required investigation areas:

1. **Current bottleneck profile**

For one representative large or medium-large feed, determine where time is actually spent.

Break down the end-to-end batch cycle into:

- Trigger-side JSON serialization
- HTTP transfer from Trigger to FastAPI
- FastAPI request-body deserialization
- COPY into staging
- merge into canonical table
- response serialization / transfer back
- Trigger-side wait before sending the next batch

You must identify which phase dominates wall time.

Requirements:

- prefer production evidence if you can obtain it safely
- if production timing evidence is unavailable, instrument or reproduce locally with a representative feed and say so explicitly
- do not hand-wave with “database is slow” or “network is slow” without a breakdown

2. **Batch size ceiling**

Determine the realistic upper bound for batch size before we hit practical limits such as:

- HTTP body size constraints
- FastAPI request parsing overhead
- Trigger or FastAPI timeouts
- Postgres transaction pressure
- memory pressure during serialization / deserialization
- COPY or merge statements becoming counterproductive

The report must explicitly assess whether batches of:

- `25000`
- `50000`
- `100000`

rows are plausible, and what would block each one.

3. **Architectural alternatives to HTTP batching**

Evaluate alternatives to “one HTTP request per batch”.

At minimum, evaluate:

- streamed request body from Trigger to FastAPI with chunked transfer semantics
- Trigger writing to an external staging area, then FastAPI merging:
  - object storage such as S3
  - Supabase Storage
  - direct Postgres staging table via direct connection
- any other architecture you believe is materially better, if it stays within the system’s current design boundaries

For each alternative, explain:

- what it would require technically
- whether it fits the existing FastAPI/Trigger boundary
- what major risks it introduces
- whether it would preserve loud failure semantics and confirmation guarantees

4. **Parallelism within a single feed**

Evaluate whether a single feed’s persistence batches could be written in parallel.

The report must address:

- safe concurrency level, if any
- whether parallel COPY+merge into the same destination table is viable
- conflict / locking risks
- transaction and idempotency implications
- whether shared tables receiving rows from multiple source variants make parallelism riskier

5. **FastAPI-side quick wins**

Identify practical server-side improvements that do not require a total architecture rewrite.

Examples to evaluate:

- connection pooling or connection reuse
- reducing per-batch schema introspection or other repeated overhead
- avoiding unnecessary per-row transformations after parsing
- COPY/merge transaction tuning
- request-body parsing overhead reductions
- timeout tuning or persistent connection behavior

Do not assume these are enough. Quantify likely impact if possible.

6. **Trigger-side quick wins**

Identify practical Trigger-side improvements that do not change the endpoint contract.

Examples to evaluate:

- HTTP connection reuse
- payload compression
- lowering JSON serialization overhead
- changing batch-flush behavior
- reducing per-batch validation overhead
- more aggressive batch sizing for selected feeds

Again, quantify likely impact if possible.

7. **Concrete recommendations ranked by impact and effort**

For each recommendation, provide:

- description
- expected impact
- implementation effort
- key risks
- whether it is a quick win, medium project, or architectural shift

The report must include both:

- near-term recommendations
- the best long-term direction if we want the 31-feed daily run to become truly feasible

Hard requirements:

- do not implement code in this directive
- do not change any files except the report document you create
- do not deploy
- do not push
- do not treat the current COPY write path as hypothetical; analyze the actual current code
- do not recommend broad architecture changes without explaining why the current FastAPI/Trigger boundary is insufficient
- if any conclusion depends on missing production metrics, say that explicitly and separate measured facts from modeled estimates

Recommended structure for `docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`:

- current architecture summary
- methodology and evidence sources
- representative feed selection and why
- bottleneck breakdown
- batch size ceiling analysis
- alternatives to per-batch HTTP
- safe parallelism analysis
- FastAPI quick wins
- Trigger quick wins
- ranked recommendations
- open questions / missing data

Commit standalone.

---

**What is NOT in scope:** No code changes. No migrations. No Trigger task rewrites. No endpoint contract changes. No deployment. No push. No final implementation of any recommendation. No unrelated FMCSA schema work.

**Commit convention:** One commit only for the diagnosis report. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`, (b) the representative feed you analyzed and why, (c) the measured or inferred bottleneck breakdown, (d) the practical batch-size ceiling you concluded, (e) the top 3 recommendations by impact, and (f) anything to flag before an implementation directive is written.
