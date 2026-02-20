-- 013_job_posting_entities.sql
-- Persistent canonical job posting intelligence snapshots.

CREATE TABLE IF NOT EXISTS job_posting_entities (
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    entity_id UUID NOT NULL,

    -- Identity
    theirstack_job_id BIGINT,
    job_url TEXT,

    -- Core fields
    job_title TEXT,
    normalized_title TEXT,
    company_name TEXT,
    company_domain TEXT,

    -- Location
    location TEXT,
    short_location TEXT,
    state_code TEXT,
    country_code TEXT,
    remote BOOLEAN,
    hybrid BOOLEAN,

    -- Job attributes
    seniority TEXT,
    employment_statuses TEXT[],
    date_posted TEXT,
    discovered_at TEXT,

    -- Salary
    salary_string TEXT,
    min_annual_salary_usd DOUBLE PRECISION,
    max_annual_salary_usd DOUBLE PRECISION,

    -- Content
    description TEXT,
    technology_slugs TEXT[],
    hiring_team JSONB,

    -- Lifecycle
    posting_status TEXT DEFAULT 'active' CHECK (posting_status IN ('active', 'likely_closed', 'confirmed_closed')),

    -- Enrichment tracking
    enrichment_confidence NUMERIC,
    last_enriched_at TIMESTAMPTZ,
    last_operation_id TEXT,
    last_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    source_providers TEXT[],
    record_version BIGINT NOT NULL DEFAULT 1 CHECK (record_version > 0),
    canonical_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_job_posting_entities PRIMARY KEY (org_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_theirstack_id
    ON job_posting_entities(org_id, theirstack_job_id);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_company_domain
    ON job_posting_entities(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_company_name
    ON job_posting_entities(org_id, company_name);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_job_title
    ON job_posting_entities(org_id, job_title);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_posting_status
    ON job_posting_entities(org_id, posting_status);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_country_code
    ON job_posting_entities(org_id, country_code);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_seniority
    ON job_posting_entities(org_id, seniority);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_company_id
    ON job_posting_entities(org_id, company_id);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_remote
    ON job_posting_entities(org_id, remote);

DROP TRIGGER IF EXISTS update_job_posting_entities_updated_at ON job_posting_entities;
CREATE TRIGGER update_job_posting_entities_updated_at
    BEFORE UPDATE ON job_posting_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE job_posting_entities ENABLE ROW LEVEL SECURITY;

ALTER TABLE entity_timeline DROP CONSTRAINT IF EXISTS entity_timeline_entity_type_check;
ALTER TABLE entity_timeline ADD CONSTRAINT entity_timeline_entity_type_check
    CHECK (entity_type IN ('company', 'person', 'job'));

ALTER TABLE entity_snapshots DROP CONSTRAINT IF EXISTS entity_snapshots_entity_type_check;
ALTER TABLE entity_snapshots ADD CONSTRAINT entity_snapshots_entity_type_check
    CHECK (entity_type IN ('company', 'person', 'job'));
