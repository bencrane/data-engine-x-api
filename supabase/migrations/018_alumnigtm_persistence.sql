-- 018_alumnigtm_persistence.sql
-- AlumniGTM pipeline dedicated persistence: new columns + tables.

-- New columns on company_entities for 1:1 pipeline output data
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS company_linkedin_id TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_criterion TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS salesnav_url TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_fit_verdict TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_fit_reasoning TEXT;
