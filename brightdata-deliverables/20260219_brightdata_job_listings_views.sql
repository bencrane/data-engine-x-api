-- Migration: Bright Data Job Listings Convenience Views
-- Created: 2026-02-19
-- Purpose: Add quick-access views for active Indeed jobs and cross-source summary stats.

CREATE OR REPLACE VIEW raw.brightdata_indeed_active_jobs AS
SELECT *
FROM raw.brightdata_indeed_job_listings
WHERE is_expired IS NOT TRUE;


CREATE OR REPLACE VIEW raw.brightdata_job_listings_summary AS
SELECT
    'indeed' AS source,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE is_expired IS TRUE) AS expired_count,
    COUNT(*) FILTER (WHERE is_expired IS NOT TRUE) AS active_count,
    MIN(ingested_at) AS earliest_ingestion,
    MAX(ingested_at) AS latest_ingestion,
    COUNT(DISTINCT ingestion_batch_id) AS batch_count
FROM raw.brightdata_indeed_job_listings
UNION ALL
SELECT
    'linkedin' AS source,
    COUNT(*) AS total_records,
    NULL AS expired_count,
    NULL AS active_count,
    MIN(ingested_at) AS earliest_ingestion,
    MAX(ingested_at) AS latest_ingestion,
    COUNT(DISTINCT ingestion_batch_id) AS batch_count
FROM raw.brightdata_linkedin_job_listings;
