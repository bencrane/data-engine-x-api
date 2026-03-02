Implemented all requested scope in 5 standalone commits (not pushed, no deploy run):
57e1178 — Deliverable 1 (tables migration)
255a3b1 — Deliverable 2 (Indeed Modal ingestion)
167d852 — Deliverable 3 (LinkedIn Modal ingestion)
849074c — Deliverable 4 (FastAPI endpoints)
39eca56 — Deliverable 5 (views migration)
(a) Table names and column counts
raw.brightdata_indeed_job_listings — 33 columns
raw.brightdata_linkedin_job_listings — 37 columns
raw.brightdata_ingestion_batches — 5 columns
(b) Ingestion function signatures
def ingest_brightdata_indeed_jobs(records: list[dict], metadata: dict | None = None) -> dict
def ingest_brightdata_linkedin_jobs(records: list[dict], metadata: dict | None = None) -> dict
(c) Upsert conflict keys
Indeed listings: jobid
LinkedIn listings: job_posting_id
(d) FastAPI endpoint paths
POST /api/ingest/brightdata/indeed
POST /api/ingest/brightdata/linkedin
(e) Index list for each table
raw.brightdata_indeed_job_listings
idx_brightdata_indeed_company_name
idx_brightdata_indeed_job_title
idx_brightdata_indeed_is_expired
idx_brightdata_indeed_ingestion_batch
idx_brightdata_indeed_ingested_at
idx_brightdata_indeed_country
idx_brightdata_indeed_region
raw.brightdata_linkedin_job_listings
idx_brightdata_linkedin_company_name
idx_brightdata_linkedin_company_id
idx_brightdata_linkedin_job_title
idx_brightdata_linkedin_ingestion_batch
idx_brightdata_linkedin_ingested_at
idx_brightdata_linkedin_job_posted_date
idx_brightdata_linkedin_country_code
idx_brightdata_linkedin_seniority
raw.brightdata_ingestion_batches
idx_brightdata_batches_source
idx_brightdata_batches_created_at
(f) Schema/pattern decisions that differ from existing HQ conventions
Used direct Postgres upsert via psycopg2 + execute_values for high-volume batch upserts, instead of Supabase client inserts/upserts used in many existing ingest endpoints.
Added a dedicated FastAPI router hq-api/routers/brightdata_ingest.py with explicit INGEST_API_KEY header guard (x-api-key) for ingestion endpoints.
Preserved required first_seen_at semantics by only updating ingested_at on conflict, while updating all structured fields + raw_payload.
(g) Anything to flag
No deploy commands were run.
No DB migrations were executed against the live database from this session; only migration files were created.
Existing unrelated local workspace changes were left intact and not reverted.
Deliverable 5 (views) was included as requested/recommended.