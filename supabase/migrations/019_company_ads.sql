-- 019_company_ads.sql
-- Persisted ad intelligence from Adyntel (LinkedIn, Meta, Google).

CREATE TABLE IF NOT EXISTS company_ads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_entity_id UUID,
    platform TEXT NOT NULL,
    ad_id TEXT,
    ad_type TEXT,
    ad_format TEXT,
    headline TEXT,
    body_text TEXT,
    cta_text TEXT,
    landing_page_url TEXT,
    media_url TEXT,
    media_type TEXT,
    advertiser_name TEXT,
    advertiser_url TEXT,
    start_date TEXT,
    end_date TEXT,
    is_active BOOLEAN,
    impressions_range TEXT,
    spend_range TEXT,
    country_code TEXT,
    raw_ad JSONB NOT NULL,
    discovered_by_operation_id TEXT NOT NULL,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup: one ad per platform per domain per org. ad_id is the platform-specific unique identifier.
-- If ad_id is null (some platforms don't provide one), allow duplicates — raw_ad JSONB is the archive.
CREATE UNIQUE INDEX IF NOT EXISTS idx_company_ads_dedup
    ON company_ads(org_id, company_domain, platform, ad_id)
    WHERE ad_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_ads_org
    ON company_ads(org_id);
CREATE INDEX IF NOT EXISTS idx_company_ads_company
    ON company_ads(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_company_ads_platform
    ON company_ads(org_id, company_domain, platform);
CREATE INDEX IF NOT EXISTS idx_company_ads_entity
    ON company_ads(org_id, company_entity_id);

DROP TRIGGER IF EXISTS update_company_ads_updated_at ON company_ads;
CREATE TRIGGER update_company_ads_updated_at
    BEFORE UPDATE ON company_ads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_ads ENABLE ROW LEVEL SECURITY;
