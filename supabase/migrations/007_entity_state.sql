-- 007_entity_state.sql
-- Persistent canonical entity intelligence snapshots.

CREATE TABLE IF NOT EXISTS company_entities (
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    entity_id UUID NOT NULL,
    canonical_domain TEXT,
    canonical_name TEXT,
    linkedin_url TEXT,
    industry TEXT,
    employee_count INT,
    employee_range TEXT,
    revenue_band TEXT,
    hq_country TEXT,
    description TEXT,
    enrichment_confidence NUMERIC,
    last_enriched_at TIMESTAMPTZ,
    last_operation_id TEXT,
    last_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    source_providers TEXT[],
    record_version BIGINT NOT NULL DEFAULT 1 CHECK (record_version > 0),
    canonical_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_company_entities PRIMARY KEY (org_id, entity_id)
);

CREATE TABLE IF NOT EXISTS person_entities (
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    entity_id UUID NOT NULL,
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    linkedin_url TEXT,
    title TEXT,
    seniority TEXT,
    department TEXT,
    work_email TEXT,
    email_status TEXT,
    phone_e164 TEXT,
    contact_confidence NUMERIC,
    last_enriched_at TIMESTAMPTZ,
    last_operation_id TEXT,
    last_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    record_version BIGINT NOT NULL DEFAULT 1 CHECK (record_version > 0),
    canonical_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_person_entities PRIMARY KEY (org_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_company_entities_org_canonical_domain
    ON company_entities(org_id, canonical_domain);

CREATE INDEX IF NOT EXISTS idx_person_entities_org_work_email
    ON person_entities(org_id, work_email);

CREATE INDEX IF NOT EXISTS idx_company_entities_org_company_id
    ON company_entities(org_id, company_id);

CREATE INDEX IF NOT EXISTS idx_person_entities_org_company_id
    ON person_entities(org_id, company_id);

CREATE INDEX IF NOT EXISTS idx_company_entities_org_industry
    ON company_entities(org_id, industry);

CREATE INDEX IF NOT EXISTS idx_person_entities_org_linkedin_url
    ON person_entities(org_id, linkedin_url);

CREATE TRIGGER update_company_entities_updated_at
    BEFORE UPDATE ON company_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_person_entities_updated_at
    BEFORE UPDATE ON person_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE person_entities ENABLE ROW LEVEL SECURITY;
