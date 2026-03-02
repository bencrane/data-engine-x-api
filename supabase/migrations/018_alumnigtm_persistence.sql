-- 018_alumnigtm_persistence.sql
-- AlumniGTM pipeline dedicated persistence: new columns + tables.

-- New columns on company_entities for 1:1 pipeline output data
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS company_linkedin_id TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_criterion TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS salesnav_url TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_fit_verdict TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_fit_reasoning TEXT;

-- Discovered customers per company (from Gemini customers-of operation)
CREATE TABLE IF NOT EXISTS company_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_entity_id UUID NOT NULL,
    company_domain TEXT NOT NULL,
    customer_name TEXT,
    customer_domain TEXT,
    customer_linkedin_url TEXT,
    customer_org_id TEXT,
    discovered_by_operation_id TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_customers_dedup
    ON company_customers(org_id, company_domain, customer_domain)
    WHERE customer_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_customers_org
    ON company_customers(org_id);
CREATE INDEX IF NOT EXISTS idx_company_customers_company
    ON company_customers(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_company_customers_entity
    ON company_customers(org_id, company_entity_id);

DROP TRIGGER IF EXISTS update_company_customers_updated_at ON company_customers;
CREATE TRIGGER update_company_customers_updated_at
    BEFORE UPDATE ON company_customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_customers ENABLE ROW LEVEL SECURITY;
