-- 015_icp_job_titles.sql
-- Raw Parallel.ai ICP job title research output per company.

CREATE TABLE IF NOT EXISTS icp_job_titles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    company_description TEXT,
    raw_parallel_output JSONB NOT NULL,
    parallel_run_id TEXT,
    processor TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_icp_job_titles_dedup
    ON icp_job_titles(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_icp_job_titles_org
    ON icp_job_titles(org_id);
CREATE INDEX IF NOT EXISTS idx_icp_job_titles_domain
    ON icp_job_titles(org_id, company_domain);

DROP TRIGGER IF EXISTS update_icp_job_titles_updated_at ON icp_job_titles;
CREATE TRIGGER update_icp_job_titles_updated_at
    BEFORE UPDATE ON icp_job_titles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE icp_job_titles ENABLE ROW LEVEL SECURITY;
