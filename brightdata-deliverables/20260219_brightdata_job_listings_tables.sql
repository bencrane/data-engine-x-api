-- Migration: Bright Data Job Listings Raw Tables
-- Created: 2026-02-19
-- Purpose: Store Bright Data Indeed + LinkedIn job listing snapshots with full raw payloads.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.brightdata_indeed_job_listings (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_batch_id        UUID NOT NULL,
    first_seen_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingested_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Natural key
    jobid                     TEXT NOT NULL,

    -- Job details
    job_title                 TEXT,
    job_type                  TEXT,
    description_text          TEXT,
    description               TEXT,
    job_description_formatted TEXT,
    benefits                  JSONB,
    qualifications            TEXT,
    salary_formatted          TEXT,
    shift_schedule            JSONB,

    -- Company
    company_name              TEXT,
    company_rating            DOUBLE PRECISION,
    company_reviews_count     INTEGER,
    company_link              TEXT,
    company_website           TEXT,

    -- Location
    location                  TEXT,
    job_location              TEXT,
    country                   TEXT,
    region                    TEXT,

    -- Dates
    date_posted               TEXT,
    date_posted_parsed        TEXT,

    -- URLs
    url                       TEXT,
    apply_link                TEXT,
    domain                    TEXT,
    logo_url                  TEXT,

    -- Status
    is_expired                BOOLEAN,

    -- Metadata
    srcname                   TEXT,
    discovery_input           JSONB,

    -- Raw payload
    raw_payload               JSONB NOT NULL,

    CONSTRAINT uq_brightdata_indeed_jobid UNIQUE (jobid)
);

CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_company_name
    ON raw.brightdata_indeed_job_listings (company_name);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_job_title
    ON raw.brightdata_indeed_job_listings (job_title);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_is_expired
    ON raw.brightdata_indeed_job_listings (is_expired);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_ingestion_batch
    ON raw.brightdata_indeed_job_listings (ingestion_batch_id);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_ingested_at
    ON raw.brightdata_indeed_job_listings (ingested_at);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_country
    ON raw.brightdata_indeed_job_listings (country);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_region
    ON raw.brightdata_indeed_job_listings (region);


CREATE TABLE IF NOT EXISTS raw.brightdata_linkedin_job_listings (
    id                         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_batch_id         UUID NOT NULL,
    first_seen_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingested_at                TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Natural key
    job_posting_id             TEXT NOT NULL,

    -- Job details
    job_title                  TEXT,
    job_summary                TEXT,
    job_seniority_level        TEXT,
    job_function               TEXT,
    job_employment_type        TEXT,
    job_industries             TEXT,
    job_base_pay_range         TEXT,
    job_description_formatted  TEXT,
    is_easy_apply              BOOLEAN,

    -- Salary (structured)
    base_salary_currency       TEXT,
    base_salary_min_amount     DOUBLE PRECISION,
    base_salary_max_amount     DOUBLE PRECISION,
    base_salary_payment_period TEXT,
    salary_standards           TEXT,

    -- Company
    company_name               TEXT,
    company_id                 TEXT,
    company_url                TEXT,
    company_logo               TEXT,

    -- Location
    job_location               TEXT,
    country_code               TEXT,

    -- Dates
    job_posted_date            TIMESTAMPTZ,
    job_posted_time            TEXT,

    -- URLs
    url                        TEXT,
    apply_link                 TEXT,

    -- Applicant info
    job_num_applicants         INTEGER,

    -- Job poster (structured)
    job_poster_name            TEXT,
    job_poster_title           TEXT,
    job_poster_url             TEXT,

    -- Application
    application_availability   BOOLEAN,

    -- Metadata
    title_id                   TEXT,
    discovery_input            JSONB,

    -- Raw payload
    raw_payload                JSONB NOT NULL,

    CONSTRAINT uq_brightdata_linkedin_job_posting_id UNIQUE (job_posting_id)
);

CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_company_name
    ON raw.brightdata_linkedin_job_listings (company_name);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_company_id
    ON raw.brightdata_linkedin_job_listings (company_id);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_job_title
    ON raw.brightdata_linkedin_job_listings (job_title);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_ingestion_batch
    ON raw.brightdata_linkedin_job_listings (ingestion_batch_id);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_ingested_at
    ON raw.brightdata_linkedin_job_listings (ingested_at);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_job_posted_date
    ON raw.brightdata_linkedin_job_listings (job_posted_date);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_country_code
    ON raw.brightdata_linkedin_job_listings (country_code);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_seniority
    ON raw.brightdata_linkedin_job_listings (job_seniority_level);


CREATE TABLE IF NOT EXISTS raw.brightdata_ingestion_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,
    record_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS idx_brightdata_batches_source
    ON raw.brightdata_ingestion_batches (source);
CREATE INDEX IF NOT EXISTS idx_brightdata_batches_created_at
    ON raw.brightdata_ingestion_batches (created_at);
