# Directive: FMCSA Ingestion Throughput Diagnosis

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA ingestion pipeline has already moved from PostgREST to direct Postgres and then to a COPY-based temp-table merge design. That fixed one major class of bottleneck, but the overall pipeline is still too slow. Medium feeds in the `2M-6M` row range are taking roughly `25-40+` minutes each. With `31` feeds scheduled daily and staggered `7` minutes apart, the current throughput makes the full daily run operationally infeasible. The likely remaining architectural bottleneck is the repeated per-batch HTTP round trip between Trigger.dev and FastAPI, but that must be diagnosed and quantified rather than assumed. This directive is findings-and-recommendations only. Do not implement changes.

**Current architecture under investigation:**

- Trigger.dev downloads and parses FMCSA feeds
- Trigger batches rows and sends them as JSON over internal HTTP
- FastAPI internal endpoints receive the batch
- FastAPI does COPY into a temp table
- FastAPI merges into the canonical table with one set-based upsert
- FastAPI returns confirmation
- Trigger sends the next batch

**Problem framing to test, not assume:** At `5000-10000` rows per batch, a large feed still requires hundreds of sequential HTTP round trips. Even if COPY+merge is efficient inside FastAPI, serialization, transfer, request parsing, and response confirmation may now dominate total wall time.

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/fmcsa-daily-diff.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/internal-api.ts`
- `/Users/benjamincrane/data-engine-x-api/app/services/fmcsa_daily_diff_common.py`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_COPY_BULK_WRITE_PLAN.md`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_DATA_PIPELINE_CONTEXT.md`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_PIPELINE_PERFORMANCE_DIAGNOSIS.md`

---

### Deliverable 1: Throughput Diagnosis and Ranked Recommendations

Create `docs/FMCSA_INGESTION_THROUGHPUT_DIAGNOSIS.md`.

This report must diagnose the current throughput bottleneck and propose ranked recommendations. It must clearly separate:

- measured findings
- inferred findings
- architectural options
- near-term quick wins
- longer-term direction

The report must answer the following questions explicitly.

#### 1. Current bottleneck profile

For one representative large feed and one representative medium feed, determine where time is actually spent.

Break down the per-batch cycle into:

- Trigger-side JSON serialization
- HTTP transfer from Trigger to FastAPI
- FastAPI request-body deserialization
- COPY into staging
- merge into canonical table
- response serialization and transfer back
- Trigger-side wait before sending the next batch

The report must identify which phase dominates wall time.

Requirements:

- prefer production evidence if safely available
- if production timing evidence is unavailable, reproduce locally with representative row shapes and say so explicitly
- do not stop at “database” or “network” as vague answers; provide a breakdown

#### 2. Batch size ceiling

Determine the maximum viable batch size before we hit practical limits such as:

- HTTP body size limits
- FastAPI request parsing pressure
- Trigger/FastAPI timeout limits
- Postgres transaction pressure
- memory pressure during serialization or deserialization
- diminishing returns from oversized COPY+merge transactions

You must explicitly assess whether these batch sizes are viable:

- `25000`
- `50000`
- `100000`

For each one, explain what the likely limiting factor is.

#### 3. Architectural alternatives to per-batch HTTP

Evaluate alternatives to the current “one HTTP round trip per batch” pattern.

At minimum, evaluate:

- streamed request body from Trigger to FastAPI using chunked transfer semantics
- Trigger writing to an intermediate staging area and then signaling FastAPI to merge:
  - S3
  - Supabase Storage
  - direct Postgres staging table via direct connection
- any other materially better architecture you believe is worth consideration

For each alternative, explain:

- what would have to change technically
- whether it fits the current FastAPI/Trigger boundary
- what risks it introduces
- whether it preserves loud failure semantics and confirmation guarantees

#### 4. Parallelism within a single feed

Evaluate whether a single feed’s batches could be written in parallel.

The report must address:

- safe concurrency level, if any
- whether parallel COPY+merge operations to the same target table are viable
- conflict and locking risks
- transaction/idempotency implications
- whether shared tables receiving rows from multiple source variants make this riskier

#### 5. FastAPI-side quick wins

Identify practical server-side improvements that do not require a total architecture rewrite.

Examples to consider:

- connection pooling or connection reuse
- caching or reusing live-table column metadata
- reducing repeated per-batch setup overhead
- removing unnecessary post-parse per-row work
- transaction / COPY / merge tuning
- request-body parsing improvements
- timeout or persistent-connection tuning

Do not assume these are sufficient. Quantify likely impact where possible.

#### 6. Trigger-side quick wins

Identify practical Trigger-side improvements that do not change the endpoint contract.

Examples to consider:

- HTTP connection reuse
- payload compression
- reduced JSON serialization overhead
- different batch-flush behavior
- lower per-batch validation overhead
- larger or smarter batch sizing for selected feeds

Again, quantify likely impact where possible.

#### 7. Concrete recommendations ranked by impact and effort

For each recommendation, provide:

- description
- expected improvement
- implementation effort
- operational risk
- whether it is a quick win, medium project, or architectural shift

The report must include both:

- near-term recommendations
- the best long-term architectural direction if the goal is to make the full `31`-feed daily run truly feasible

Hard requirements:

- do not implement code in this directive
- do not modify any code, configs, migrations, or schedules
- do not deploy
- do not push
- do not assume the HTTP round trip is the bottleneck without quantifying it
- do not treat the current COPY path as hypothetical; analyze the current code path as it exists now
- if any conclusion depends on missing production metrics, say so explicitly and separate measured facts from modeled estimates

Recommended structure for `docs/FMCSA_INGESTION_THROUGHPUT_DIAGNOSIS.md`:

- current architecture summary
- methodology and evidence sources
- representative feed selection
- bottleneck breakdown
- batch-size ceiling analysis
- alternatives to per-batch HTTP
- safe parallelism analysis
- FastAPI quick wins
- Trigger quick wins
- ranked recommendations
- open questions / missing data

Commit standalone.

---

**What is NOT in scope:** No code changes. No migrations. No Trigger task rewrites. No endpoint contract changes. No deployment. No push. No implementation of recommendations. No unrelated FMCSA schema or persistence work.

**Commit convention:** One commit only. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_INGESTION_THROUGHPUT_DIAGNOSIS.md`, (b) the representative feeds analyzed and why, (c) the measured or inferred bottleneck breakdown, (d) the practical batch-size ceiling you concluded, (e) the top 3 recommendations by impact, and (f) anything to flag before an implementation directive is written.
