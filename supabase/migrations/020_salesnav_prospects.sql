-- 020_salesnav_prospects.sql
-- Alumni/prospect data from LinkedIn Sales Navigator scrapes.

CREATE TABLE IF NOT EXISTS salesnav_prospects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,

    -- The person
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    linkedin_url TEXT,
    profile_urn TEXT,
    geo_region TEXT,
    summary TEXT,
    current_title TEXT,
    current_company_name TEXT,
    current_company_id TEXT,
    current_company_industry TEXT,
    current_company_location TEXT,
    position_start_month INT,
    position_start_year INT,
    tenure_at_position_years INT,
    tenure_at_position_months INT,
    tenure_at_company_years INT,
    tenure_at_company_months INT,
    open_link BOOLEAN,

    -- Source context: which company were they found at, via what query
    source_company_domain TEXT NOT NULL,
    source_company_name TEXT,
    source_salesnav_url TEXT,

    -- Lineage
    discovered_by_operation_id TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    -- Raw archive
    raw_person JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup: one person per company per org, identified by LinkedIn URL
CREATE UNIQUE INDEX IF NOT EXISTS idx_salesnav_prospects_dedup
    ON salesnav_prospects(org_id, source_company_domain, linkedin_url)
    WHERE linkedin_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_org
    ON salesnav_prospects(org_id);
CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_source_company
    ON salesnav_prospects(org_id, source_company_domain);
CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_linkedin
    ON salesnav_prospects(org_id, linkedin_url);
CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_title
    ON salesnav_prospects(org_id, current_title);

DROP TRIGGER IF EXISTS update_salesnav_prospects_updated_at ON salesnav_prospects;
CREATE TRIGGER update_salesnav_prospects_updated_at
    BEFORE UPDATE ON salesnav_prospects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE salesnav_prospects ENABLE ROW LEVEL SECURITY;
