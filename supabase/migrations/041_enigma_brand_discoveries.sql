SET statement_timeout = '0';
BEGIN;

-- Enigma brand discovery results — one row per brand per discovery run, org-scoped
CREATE TABLE IF NOT EXISTS entities.enigma_brand_discoveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scoping
    org_id UUID NOT NULL,
    company_id UUID,

    -- Discovery context
    discovery_prompt TEXT NOT NULL,
    geography_state TEXT,
    geography_city TEXT,

    -- Brand data (Core tier)
    enigma_brand_id TEXT NOT NULL,
    brand_name TEXT,
    brand_website TEXT,
    location_count INTEGER,
    industries JSONB,

    -- Card revenue (Plus tier, populated if enrichment ran)
    annual_card_revenue NUMERIC,
    annual_card_revenue_yoy_growth NUMERIC,
    annual_avg_daily_customers NUMERIC,
    annual_transaction_count NUMERIC,
    monthly_revenue JSONB,

    -- Source tracking
    discovered_by_operation_id TEXT DEFAULT 'company.search.enigma.brands',
    source_submission_id UUID,
    source_pipeline_run_id UUID,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one brand per discovery prompt per org
CREATE UNIQUE INDEX IF NOT EXISTS idx_enigma_brand_disc_upsert_key
    ON entities.enigma_brand_discoveries (org_id, enigma_brand_id, discovery_prompt);

CREATE INDEX IF NOT EXISTS idx_enigma_brand_disc_org
    ON entities.enigma_brand_discoveries (org_id);

CREATE INDEX IF NOT EXISTS idx_enigma_brand_disc_brand
    ON entities.enigma_brand_discoveries (enigma_brand_id);

CREATE INDEX IF NOT EXISTS idx_enigma_brand_disc_prompt
    ON entities.enigma_brand_discoveries (org_id, discovery_prompt);

-- Per-location enrichment results, org-scoped, linked to brand discoveries
CREATE TABLE IF NOT EXISTS entities.enigma_location_enrichments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scoping
    org_id UUID NOT NULL,
    company_id UUID,

    -- Parent brand reference
    enigma_brand_id TEXT NOT NULL,
    brand_name TEXT,

    -- Location data (Core tier)
    enigma_location_id TEXT NOT NULL,
    location_name TEXT,
    full_address TEXT,
    street TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    operating_status TEXT,
    phone TEXT,
    website TEXT,

    -- Card transactions (Plus tier)
    annual_card_revenue NUMERIC,
    annual_card_revenue_yoy_growth NUMERIC,
    annual_avg_daily_customers NUMERIC,
    annual_transaction_count NUMERIC,

    -- Competitive rank (Plus tier)
    competitive_rank INTEGER,
    competitive_rank_total INTEGER,

    -- Reviews (Plus tier)
    review_count INTEGER,
    review_avg_rating NUMERIC,

    -- Contacts (Plus tier, stored as JSONB array)
    contacts JSONB,

    -- Source tracking
    enriched_by_operation_id TEXT DEFAULT 'company.enrich.locations',
    source_submission_id UUID,
    source_pipeline_run_id UUID,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one location per brand per org
CREATE UNIQUE INDEX IF NOT EXISTS idx_enigma_loc_enrich_upsert_key
    ON entities.enigma_location_enrichments (org_id, enigma_brand_id, enigma_location_id);

CREATE INDEX IF NOT EXISTS idx_enigma_loc_enrich_org
    ON entities.enigma_location_enrichments (org_id);

CREATE INDEX IF NOT EXISTS idx_enigma_loc_enrich_brand
    ON entities.enigma_location_enrichments (enigma_brand_id);

CREATE INDEX IF NOT EXISTS idx_enigma_loc_enrich_state
    ON entities.enigma_location_enrichments (state);

COMMIT;
