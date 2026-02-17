-- 009_entity_timeline.sql
-- Per-entity operation lineage for audit/debug visibility.

CREATE TABLE IF NOT EXISTS entity_timeline (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person')),
    entity_id UUID NOT NULL,
    operation_id TEXT NOT NULL,
    pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    provider TEXT,
    status TEXT NOT NULL CHECK (status IN ('found', 'not_found', 'failed', 'skipped')),
    fields_updated TEXT[],
    summary TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_timeline_lookup
    ON entity_timeline(org_id, entity_type, entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_timeline_pipeline_run
    ON entity_timeline(org_id, pipeline_run_id);

ALTER TABLE entity_timeline ENABLE ROW LEVEL SECURITY;
