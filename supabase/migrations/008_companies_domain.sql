-- 008_companies_domain.sql
-- Add domain field to tenant companies table.

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS domain TEXT;

CREATE INDEX IF NOT EXISTS idx_companies_org_domain
    ON companies(org_id, domain);
