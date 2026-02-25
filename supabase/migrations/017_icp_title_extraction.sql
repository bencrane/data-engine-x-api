ALTER TABLE icp_job_titles
ADD COLUMN IF NOT EXISTS extracted_titles JSONB;

CREATE TABLE IF NOT EXISTS extracted_icp_job_title_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    title TEXT NOT NULL,
    title_normalized TEXT GENERATED ALWAYS AS (LOWER(TRIM(title))) STORED,
    buyer_role TEXT,
    reasoning TEXT,
    source_icp_job_titles_id UUID REFERENCES icp_job_titles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_icp_title_details_org_domain
    ON extracted_icp_job_title_details(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_icp_title_details_org_title_normalized
    ON extracted_icp_job_title_details(org_id, title_normalized);
CREATE INDEX IF NOT EXISTS idx_icp_title_details_org_buyer_role
    ON extracted_icp_job_title_details(org_id, buyer_role);
CREATE INDEX IF NOT EXISTS idx_icp_title_details_source
    ON extracted_icp_job_title_details(source_icp_job_titles_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_icp_title_details_dedup
    ON extracted_icp_job_title_details(org_id, company_domain, title_normalized);

DROP TRIGGER IF EXISTS update_icp_title_details_updated_at ON extracted_icp_job_title_details;
CREATE TRIGGER update_icp_title_details_updated_at
    BEFORE UPDATE ON extracted_icp_job_title_details
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE extracted_icp_job_title_details ENABLE ROW LEVEL SECURITY;
