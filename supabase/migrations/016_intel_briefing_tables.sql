-- 016_intel_briefing_tables.sql
-- Raw Parallel.ai company/person intel briefing output per org entity lens.

CREATE TABLE IF NOT EXISTS company_intel_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    client_company_name TEXT,
    client_company_domain TEXT,
    client_company_description TEXT,
    raw_parallel_output JSONB NOT NULL,
    parallel_run_id TEXT,
    processor TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_intel_briefings_dedup
    ON company_intel_briefings(org_id, company_domain, client_company_name);
CREATE INDEX IF NOT EXISTS idx_company_intel_briefings_org
    ON company_intel_briefings(org_id);
CREATE INDEX IF NOT EXISTS idx_company_intel_briefings_domain
    ON company_intel_briefings(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_company_intel_briefings_client
    ON company_intel_briefings(org_id, client_company_name);

DROP TRIGGER IF EXISTS update_company_intel_briefings_updated_at ON company_intel_briefings;
CREATE TRIGGER update_company_intel_briefings_updated_at
    BEFORE UPDATE ON company_intel_briefings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_intel_briefings ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS person_intel_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    person_linkedin_url TEXT,
    person_full_name TEXT NOT NULL,
    person_current_company_name TEXT,
    person_current_company_domain TEXT,
    person_current_job_title TEXT,
    client_company_name TEXT,
    client_company_domain TEXT,
    client_company_description TEXT,
    customer_company_name TEXT,
    customer_company_domain TEXT,
    raw_parallel_output JSONB NOT NULL,
    parallel_run_id TEXT,
    processor TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_person_intel_briefings_dedup
    ON person_intel_briefings(org_id, person_full_name, person_current_company_name, client_company_name);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_org
    ON person_intel_briefings(org_id);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_linkedin
    ON person_intel_briefings(org_id, person_linkedin_url);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_company
    ON person_intel_briefings(org_id, person_current_company_name);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_client
    ON person_intel_briefings(org_id, client_company_name);

DROP TRIGGER IF EXISTS update_person_intel_briefings_updated_at ON person_intel_briefings;
CREATE TRIGGER update_person_intel_briefings_updated_at
    BEFORE UPDATE ON person_intel_briefings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE person_intel_briefings ENABLE ROW LEVEL SECURITY;
