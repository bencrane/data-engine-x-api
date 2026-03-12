# FMCSA Pipeline Performance Diagnosis

## Current Architecture Summary

The current FMCSA ingest path is:

1. Trigger.dev downloads one FMCSA feed.
2. Trigger parses the source file and normalizes each row into the FMCSA batch payload shape.
3. Trigger groups rows into batches, serializes each batch to JSON, and POSTs it to a FastAPI internal endpoint.
4. FastAPI validates the JSON body into `InternalUpsertFmcsaDailyDiffBatchRequest`.
5. FastAPI converts each row into typed table columns, opens a direct Postgres connection, creates a temp table, `COPY`s the batch into staging, merges staging into the canonical `entities.*` table with one `INSERT ... SELECT ... ON CONFLICT DO UPDATE`, commits, and returns a confirmation envelope.
6. Trigger waits for the confirmation before continuing to the next batch.

This is not hypothetical. The current code in `trigger/src/workflows/fmcsa-daily-diff.ts`, `trigger/src/workflows/internal-api.ts`, `app/routers/internal.py`, and `app/services/fmcsa_daily_diff_common.py` is already on the JSON-over-internal-HTTP plus temp-table `COPY` plus set-based merge design.

## Methodology And Evidence Sources

This report separates measured evidence from inference.

### Measured

- Current Trigger workflow code and FastAPI write-path code.
- Trigger.dev prod run history for the two heaviest current CSV feeds:
  - `fmcsa-company-census-file-daily`
  - `fmcsa-vehicle-inspection-file-daily`
- Trigger.dev prod run details for representative failed runs:
  - `run_cmmme1egu6kqk0onc14ge33ea` (`Company Census File`)
  - `run_cmmme1egq6pzx0on1kg7do6y3` (`Vehicle Inspection File`)
- Socrata count query for representative feed size:
  - `Company Census File`: `4,402,459` rows
  - `Vehicle Inspection File`: `8,182,384` rows
- Local benchmark on a real public `Company Census File` sample (`100,000` rows, `147` columns) measuring:
  - row parsing / raw-row construction
  - JSON serialization size and time
  - localhost HTTP POST body read
  - Python `json.loads`
  - Pydantic validation of the current request shape
  - gzip compression ratio and CPU cost
- Local payload-size benchmark on a medium-width feed:
  - `InsHist - All With History`

### Not Measured Directly

- Production FastAPI per-phase timing split between:
  - request-body parse
  - row-builder typing
  - temp-table creation
  - `COPY`
  - merge
  - commit
- Production Postgres query stats for the FMCSA endpoints

The Postgres MCP was not usable during this investigation because connection attempts failed or timed out. Because of that, the exact `COPY` vs merge split below is inferred from code shape plus Trigger timeout behavior, not directly measured in production.

## Representative Feed Selection And Why

I used `Company Census File` as the primary representative feed.

Why this feed:

- It is in the requested problematic range: `4,402,459` rows.
- It is one of the two explicitly tuned wide CSV feeds with `writeBatchSize: 10000`.
- It is the widest current feed shape in the fleet (`147` source columns), so it is the worst-case JSON payload driver.
- It already has recent prod evidence showing persistence failures and timeouts on the current architecture.
- It writes into `entities.motor_carrier_census_records`, a shared canonical table that also receives a narrower SMS feed, so it is a realistic example of both payload size and shared-table persistence pressure.

`Vehicle Inspection File` shows the same failure class, but at `8.18M` rows it is beyond the `2-6M` range named in the prompt. I still use it as corroborating evidence, not as the primary representative feed.

## Bottleneck Breakdown

## Measured Local Phase Costs For `Company Census File`

Local benchmark setup:

- Real public sample from `Company Census File`
- `100,000` rows parsed from the live Socrata CSV export
- Same FMCSA row payload shape as current Trigger code:
  - `row_number`
  - `raw_values`
  - `raw_fields`
- Same outer request envelope shape as current FastAPI endpoint
- Python `3.14`, Pydantic `2.12`
- Localhost HTTP stub only for transport/body-read validation

### Per-10k batch

| Phase | Measurement | Notes |
|---|---:|---|
| Trigger CSV parse + raw row object construction | `~1.19s` | `100,000` rows parsed in `11.903s` |
| Trigger JSON serialization | `2.697s` | `35.22 MB` request body |
| Local HTTP body read on server | `0.012s` | loopback only, not prod network |
| FastAPI-side JSON deserialization proxy (`json.loads`) | `0.551s` | same request shape |
| FastAPI-side Pydantic validation proxy | `0.124s` | same request shape |
| FastAPI-side typed row builder proxy | `0.374s` | equivalent to `_build_company_census_row()` |
| Response serialization / write | negligible | tiny response envelope |

Total measured non-DB CPU for a representative 10k wide batch is roughly `4.0s` on a laptop, with the dominant client-side cost being JSON serialization.

### Payload and memory behavior by batch size for `Company Census File`

| Batch size | JSON size | `json.dumps` | `json.loads` | Pydantic validate | Peak alloc during dumps | Peak alloc during loads |
|---|---:|---:|---:|---:|---:|---:|
| `10000` | `35.22 MB` | `2.697s` | `0.551s` | `0.124s` | `40.43 MB` | `67.76 MB` |
| `25000` | `88.03 MB` | `6.729s` | `1.460s` | `0.320s` | `98.70 MB` | `168.98 MB` |
| `50000` | `176.33 MB` | `13.577s` | `2.934s` | `0.647s` | `192.77 MB` | `339.12 MB` |
| `100000` | `353.72 MB` | `27.354s` | `6.231s` | `1.337s` | `376.50 MB` | `682.40 MB` |

Additional measured request-compression result for `Company Census File`:

| Batch size | Raw JSON | Gzip size | Ratio | Compress CPU | Decompress CPU |
|---|---:|---:|---:|---:|---:|
| `10000` | `35.22 MB` | `2.27 MB` | `6.4%` of raw | `0.231s` | `0.044s` |
| `25000` | `88.03 MB` | `5.67 MB` | `6.4%` of raw | `0.592s` | `0.039s` |

## Corroborating Prod Evidence

Recent Trigger prod runs show the same endpoint failing under real load:

- `Company Census File`:
  - recent prod runs are taking roughly `59.6m` to `1.2h`
  - failures include:
    - internal `502` on `/api/internal/motor-carrier-census-records/upsert-batch`
    - persistence timeout after `300000ms`
- `Vehicle Inspection File`:
  - recent prod runs are taking roughly `1.0h` to `1.1h`
  - failures include:
    - persistence timeout after `300000ms`

In the representative prod `Company Census File` run, the trace shows repeated `fmcsa streaming batch persist` events roughly every `40-45s` early in the run, then much larger stalls later, including gaps of about `191s` and `397s`, followed by a `300s` request timeout. The same pattern appears in `Vehicle Inspection File`.

## Diagnosis

### What is measured with high confidence

- The current wide-feed request body is already very large at `10000` rows:
  - `35.22 MB` uncompressed for `Company Census File`
- JSON serialization is not free:
  - `2.697s` per 10k batch on the client side
- FastAPI request parsing and validation are real but comparatively small:
  - `~0.675s` combined for `json.loads` + Pydantic at 10k
- Pure Python row typing is also comparatively small:
  - `0.374s` for 10k company-census rows
- Production batch cycles are much slower than these measured transport/parse costs:
  - repeatedly `40-45s`
  - sometimes `191-397s`
  - sometimes hard-failing at `300s`

### What follows from those measurements

For the representative wide feed, the dominant wall time is not Trigger-side JSON work by itself and not FastAPI request parsing by itself. Those costs are material, but they are too small to explain the observed production batch waits.

The current bottleneck is the synchronous per-batch persistence round trip as a whole, with the server-side persistence work inside that round trip dominating:

- connection acquisition / connection setup
- temp-table creation
- `COPY` into staging
- merge into the indexed canonical table
- commit
- any DB backpressure / queueing / lock wait on the target table and indexes

The exact split between `COPY` and merge is not directly measured here. Based on the code shape, the merge is the most likely heavier sub-phase because:

- `COPY` is a sequential append into a temp table
- the merge touches the real indexed canonical table
- the merge performs conflict checks and update assignments against the target uniqueness path and secondary indexes
- the current prod symptoms are long waits and 300s timeouts on the persistence request, not client CPU saturation

### Direct answer to the prompt’s hypothesis

The per-batch HTTP round trip is a real architectural tax and it is still one of the reasons the overall design does not scale. But for the current heaviest wide feeds, the bottleneck is not just “network overhead.” The evidence says:

- the JSON-over-HTTP contract creates very large request bodies and too many sequential confirmations
- but the decisive per-batch wall time today is the server-side persistence wait inside that request
- therefore simply increasing batch size inside the current contract will not make the problem disappear

In short: the current boundary is insufficient because it combines both problems:

1. too many sequential request/confirmation steps
2. too much per-request server-side persistence time

## Why The Current Contract Cannot Make The 31-Feed Schedule Feasible

For the representative feed:

- `Company Census File` row count: `4,402,459`
- with `10000` rows per batch: about `441` sequential requests

To finish that feed in:

- `30 minutes`, the end-to-end average budget is only `~4.1s` per batch
- `40 minutes`, the budget is only `~5.4s` per batch

But the measured non-DB work alone for a 10k wide batch is already about `4.0s`, before the real persistence work. That means the current contract leaves almost no time budget for database work at all if the target is a truly feasible daily run.

Even if prod batch time dropped from `40s` to `10s`, this feed would still take about `73 minutes` at `10000` rows per batch.

This is why the long-term answer cannot be “just tune one timeout” or “just make JSON a little faster.”

## Batch Size Ceiling Analysis

There is no single safe row-count ceiling across all 31 feeds because payload width varies drastically by feed family. The current row-based batching is masking that reality.

### Evidence that row-count-only batching is misleading

Measured JSON body sizes:

- `Company Census File` (`147` columns, very wide):
  - `10000` rows -> `35.22 MB`
  - `25000` rows -> `88.03 MB`
  - `50000` rows -> `176.33 MB`
  - `100000` rows -> `353.72 MB`
- `InsHist - All With History` (medium width):
  - `10000` rows -> `7.63 MB`
  - `25000` rows -> `19.25 MB`
  - `50000` rows -> `38.50 MB`
  - `100000` rows -> `77.04 MB`

The same row count can produce bodies that differ by more than `4x`.

## Assessment Of `25000`, `50000`, `100000`

### `25000` rows

#### Wide feeds such as `Company Census File`

Borderline at best under the current contract.

What blocks it:

- `88 MB` uncompressed request bodies are already uncomfortably large
- client-side JSON serialization alone is `6.7s`
- server-side JSON parse + validation is another `~1.8s`
- peak transient allocations are already large:
  - `~99 MB` during serialization
  - `~169 MB` during loads
  - `~121 MB` during validation
- current prod wide-feed persistence is already timing out at `10000`, so making the DB batch `2.5x` larger is not a credible near-term fix

Conclusion:

- `25000` is not a safe general recommendation for the widest feeds under the current JSON-over-HTTP contract
- it may become plausible only with request compression plus clear proof that the server-side merge can handle it

#### Medium-width feeds

Potentially plausible.

Example:

- `InsHist - All With History` at `25000` rows is only `19.25 MB`

Conclusion:

- `25000` is plausible for narrower and medium-width feeds if request size is kept under a byte budget and the endpoint’s DB phase is proven safe
- it should not be adopted as a single fleet-wide default

### `50000` rows

Not plausible as a fleet-wide setting under the current contract.

What blocks it for wide feeds:

- `176 MB` uncompressed request body
- `13.6s` client JSON serialization
- `2.9s` JSON parse before validation
- `~339 MB` peak allocation during loads alone
- local localhost POSTs started failing with socket buffer pressure in this size class
- current prod wide-feed DB writes already exceed `300s` timeouts at `10000`

Conclusion:

- `50000` is not a practical current-contract target for wide feeds
- for medium-width feeds it might be technically possible, but only after explicit byte-budgeting, compression, and endpoint timing proof
- as a general FMCSA default it is not prudent

### `100000` rows

Not plausible under the current JSON-over-HTTP contract for production FMCSA ingest.

What blocks it:

- `353.72 MB` uncompressed wide-feed body
- `27.4s` client serialization before the request even goes out
- `6.2s` JSON parse on the server side before validation
- `~682 MB` peak allocation during loads, plus the body string itself, plus validation allocations
- the request becomes dominated by memory and body-size risk before DB work even starts
- any realistic DB merge time makes total request time unacceptable

Conclusion:

- `100000` rows is not a credible target for the current architecture

## Practical Batch Ceiling Conclusion

Under the current endpoint contract, the real ceiling should be byte-based, not row-based.

Practical conclusion:

- wide feeds: keep around the current `10000` range until the architecture changes
- medium-width feeds: `25000` may be reasonable after targeted proof
- `50000+` should be treated as exceptional and feed-specific, not a normal FMCSA default
- `100000` is not practical for current JSON-over-HTTP FMCSA writes

If forced to pick one current-contract upper bound that is safe across the fleet, it is closer to the present `10000` than to `25000`.

## Alternatives To Per-Batch HTTP

## 1. Streamed request body from Trigger to FastAPI

### What it requires

- Trigger must send a streaming body instead of one prebuilt JSON string
- FastAPI must stop relying on Pydantic body binding for the bulk endpoint and instead read `request.stream()`
- the payload format should change from giant JSON arrays to streamable NDJSON or streamed CSV-like chunks
- FastAPI would need incremental decoding and incremental staging writes

### Fit with current boundary

- It stays inside the Trigger -> FastAPI boundary
- FastAPI still owns DB writes

### Risks

- much more custom request-handling code
- harder request validation story
- long-lived HTTP request behavior becomes critical
- proxy buffering or request-timeout behavior can still sink the design
- retry/restart semantics are worse than current per-batch confirmation unless a staging manifest is introduced

### Failure semantics

Loud failure semantics can be preserved if FastAPI stages all streamed rows into a temp or durable staging area and only confirms success after final row-count validation plus merge. That is possible, but more complicated than the current confirmed-write pattern.

### Verdict

Better than current giant JSON arrays, but not the best long-term answer. It reduces memory pressure and body-size overhead, but it still relies on a long-running HTTP request as the core ingest transport.

## 2. Trigger writes a staged artifact, FastAPI ingests by reference

Possible staging targets:

- S3
- Supabase Storage

### What it requires

- Trigger writes a gzipped NDJSON or CSV artifact to object storage
- Trigger sends FastAPI a small manifest:
  - feed metadata
  - object location
  - checksum
  - row count
- FastAPI downloads the artifact server-side and performs local parse + `COPY` + merge

### Fit with current boundary

- Strong fit
- Trigger remains orchestrator
- FastAPI remains DB owner
- the boundary becomes “manifest + confirmation” rather than “every row serialized across services”

### Risks

- object lifecycle / cleanup
- need for checksum and row-count discipline
- extra storage cost
- additional artifact management complexity

### Failure semantics

This preserves loud failure semantics well:

- Trigger can refuse to continue until FastAPI confirms:
  - checksum match
  - rows received
  - rows written
- partial artifacts can be quarantined or retried explicitly

### Verdict

This is the best architectural option that stays within the current FastAPI/Trigger ownership boundary.

## 3. Trigger writes directly to Postgres staging

### What it requires

- DB credentials in Trigger
- staging-table creation from Trigger
- merge logic either duplicated in Trigger or moved to shared SQL utilities
- operational ownership split between Trigger and FastAPI

### Fit with current boundary

- Weak fit
- It breaks the current rule that FastAPI owns DB writes

### Risks

- secret sprawl
- dual write-path ownership
- more places where schema drift can break ingest
- less centralized observability for persistence

### Failure semantics

It can still fail loudly if Trigger manages one transaction and explicit confirmation, but the design is a deliberate architectural exception.

### Verdict

Highest raw throughput potential, but not the best fit for the current system boundaries.

## 4. Move the heavy ingest loop server-side and let Trigger schedule/monitor only

### What it requires

- Trigger sends only feed metadata or start-job metadata
- FastAPI or a DB-adjacent worker performs:
  - source download
  - parse
  - `COPY`
  - merge
- job status becomes an internal job record rather than a giant synchronous POST body exchange

### Fit with current boundary

- Better fit than direct Trigger -> Postgres
- FastAPI still owns DB writes
- but it changes the responsibility split: Trigger no longer transports bulk row payloads

### Risks

- long-running job execution has to be handled somewhere safe
- if done inside normal Railway request handling, it can create a new bottleneck
- likely needs a worker/job abstraction

### Failure semantics

Strong loud-failure semantics are possible if the job writes explicit state and row-count confirmations.

### Verdict

Best long-term direction if the goal is to make the 31-feed daily run genuinely feasible. It removes the most expensive cross-service data transport entirely.

## Safe Parallelism Analysis

## Can a single feed write batches in parallel today?

Technically yes, but operationally it is a bad near-term bet.

Why it is technically possible:

- each request already creates its own temp table
- disjoint batch ranges for the same feed have disjoint `(feed_date, source_feed_name, row_position)` keys
- idempotency is source-slot based, so deterministic batch partitioning is possible

Why it is still risky:

- concurrent merges still hit the same canonical destination table and indexes
- shared tables such as:
  - `entities.motor_carrier_census_records`
  - `entities.carrier_inspections`
  - `entities.carrier_inspection_violations`
  are already written by multiple source variants
- more concurrent merges mean more WAL, more index pressure, more lock waits, and more chances to worsen the exact timeout behavior already seen at concurrency `1`

## Safe concurrency level

For the current architecture, recommended safe concurrency per feed is:

- current recommendation: `1`
- possible later experimental ceiling: `2`, only after direct DB timing instrumentation proves the single-stream path is healthy

I would not recommend higher concurrency within one feed under the present design.

## Idempotency and retry implications

Parallelism would require:

- deterministic non-overlapping batch ranges
- explicit batch identifiers in logs and confirmations
- clear retry semantics for partial feed completion

The uniqueness key helps, but it does not remove the observability and backpressure risks.

## Conclusion on parallelism

Parallelism inside one feed is not the next lever to pull. The current single-stream path is already timing out. Fix the boundary and persistence timing first.

## FastAPI-Side Quick Wins

These are improvements that do not require a full redesign.

## 1. Add real phase instrumentation

Add explicit timers for:

- request-body bytes
- request parse time
- row-builder time
- connection acquisition time
- temp-table create time
- `COPY` time
- merge time
- commit time

Expected impact:

- no direct throughput gain
- high decision value

Why it matters:

- today the exact `COPY` vs merge split is inferred, not measured

## 2. Reuse Postgres connections instead of opening one per batch

Current code calls `connect(settings.database_url)` per batch write.

Expected impact:

- likely small to modest per batch
- maybe tens to a few hundreds of milliseconds saved per batch
- multiplied by hundreds of batches, this can still save minutes per feed

Why it is not the main fix:

- it cannot explain `40s-300s` batch waits

## 3. Support gzipped request bodies

Expected impact:

- meaningful reduction in request transfer size
- likely helpful for body-read overhead and infrastructure pressure

Measured evidence:

- `35.22 MB` -> `2.27 MB` at 10k
- `88.03 MB` -> `5.67 MB` at 25k
- low CPU overhead

Why it is still not enough alone:

- it does not fix the DB merge cost that is already timing out at 10k on wide feeds

## 4. Reduce request parsing overhead only if cheap

Examples:

- faster JSON parser
- lighter-weight internal body validation
- partial trust of internal payload shape

Expected impact:

- small

Measured evidence:

- request parse + validation is under `1s` at 10k in the representative wide case

## 5. Treat row-builder CPU as tertiary

Measured evidence:

- `0.374s` for `10000` `Company Census File` rows

Conclusion:

- not a primary bottleneck

## Trigger-Side Quick Wins

## 1. Request compression

This is the strongest Trigger-side quick win.

Measured evidence:

- `Company Census File` `10000` rows:
  - `35.22 MB` raw
  - `2.27 MB` gzipped
  - `0.231s` compression CPU
- `25000` rows:
  - `88.03 MB` raw
  - `5.67 MB` gzipped
  - `0.592s` compression CPU

Expected impact:

- materially lower on-wire size
- lower request-body pressure
- lower risk of proxy/body-size issues

## 2. Replace row-count batching with byte-budget batching

Current problem:

- `10000` rows can mean `7.6 MB` for a medium feed or `35.2 MB` for a wide feed

Recommendation:

- batch by estimated serialized bytes, not rows alone

Expected impact:

- lets narrow feeds use larger row counts safely
- prevents wide feeds from silently generating pathological request bodies

## 3. Overlap parsing/serialization with the previous batch’s persistence wait

Current code stops the parser loop at `await flushBatch()`.

Expected impact:

- modest but real
- can overlap some client CPU work with the server-side wait

Why it is secondary:

- it does not reduce the server-side persistence time itself

## 4. HTTP connection reuse is probably already mostly there

Current code:

- one `InternalApiClient` instance per workflow
- Node `fetch` on modern runtimes typically already reuses connections

Expected impact:

- low

## Ranked Recommendations

## 1. Long-term: stop shipping FMCSA row payloads batch-by-batch over internal HTTP

Description:

- Move heavy FMCSA ingest to either:
  - staged artifact + FastAPI ingest by reference
  - server-side ingest job with Trigger only scheduling/monitoring

Expected impact:

- highest
- this is the only direction that removes both:
  - hundreds of sequential confirmations
  - giant cross-service row payloads

Implementation effort:

- high

Risks:

- new artifact/job lifecycle
- more ingest orchestration logic

Category:

- architectural shift

## 2. Near-term: add gzip request compression and byte-budget batching

Description:

- compress internal FMCSA write requests
- batch by serialized byte target instead of raw row count
- keep wide feeds conservative while allowing narrower feeds to batch more aggressively

Expected impact:

- medium to high
- strongest quick win available without breaking the endpoint boundary

Implementation effort:

- low to medium

Risks:

- request decompression support must be correct
- byte estimator needs validation

Category:

- quick win

## 3. Near-term: instrument every FastAPI persistence phase and reuse DB connections

Description:

- add phase timers and request-size logging
- stop opening a fresh direct Postgres connection for every FMCSA batch if feasible

Expected impact:

- low to medium on throughput
- very high on diagnosis quality

Implementation effort:

- low to medium

Risks:

- low

Category:

- quick win

## 4. Medium-term: do not increase wide-feed batch sizes until server-side timing proves it is safe

Description:

- keep wide feeds near current `10000`
- use evidence before trying `25000`

Expected impact:

- prevents a likely regression

Implementation effort:

- low

Risks:

- low

Category:

- quick win

## 5. Medium-term: consider producer/consumer overlap in Trigger

Description:

- parse/prepare the next batch while the current batch is being persisted

Expected impact:

- modest

Implementation effort:

- medium

Risks:

- queue complexity
- memory discipline

Category:

- medium project

## Best Long-Term Direction

If the real goal is to make the 31-feed daily run operationally feasible, the best long-term direction is:

- Trigger schedules and monitors
- FastAPI or a DB-adjacent ingest worker owns the heavy download/parse/`COPY`/merge loop
- or Trigger writes one staged artifact and FastAPI ingests it by reference

Why:

- the current FastAPI/Trigger boundary is too chatty and too heavy
- even perfect JSON tuning does not recover enough budget when a representative `4.4M` row feed has `441` sequential 10k confirmations
- the current contract forces the largest payloads to cross the service boundary repeatedly, which is the wrong shape for this workload

## Open Questions / Missing Data

- Exact production split between:
  - request parse
  - row typing
  - `COPY`
  - merge
  - commit
- Actual prod request-body/proxy limits on the current Railway path
- Whether FastAPI request decompression is already available in the deployed stack or would need explicit middleware support
- Exact keep-alive behavior observed between Trigger and FastAPI in production
- How much destination-table index maintenance is contributing for:
  - `motor_carrier_census_records`
  - `carrier_inspections`

## Bottom Line

The current COPY-based FastAPI write path removed the old row-oriented DB bottleneck, but it did not make the overall ingest shape scalable enough for the heaviest FMCSA feeds.

For the representative `Company Census File` feed:

- the dataset is `4,402,459` rows
- the current `10000`-row batch shape already produces `35.22 MB` JSON bodies
- measured JSON + parse + validation + row-builder cost is about `4s` per batch before DB work
- prod batch waits are still `40s-300s`

So the dominant problem now is the synchronous batch confirmation loop, with server-side persistence time dominating inside that loop. The near-term wins are compression, byte-budget batching, and instrumentation. The real long-term fix is to stop relaying FMCSA rows across the Trigger -> FastAPI boundary one JSON batch at a time.
