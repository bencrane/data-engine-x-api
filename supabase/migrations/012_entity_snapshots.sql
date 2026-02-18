CREATE TABLE IF NOT EXISTS entity_snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person')),
    entity_id UUID NOT NULL,
    record_version BIGINT NOT NULL,
    canonical_payload JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    CONSTRAINT uq_entity_snapshot_version UNIQUE (org_id, entity_type, entity_id, record_version)
);

CREATE INDEX IF NOT EXISTS idx_entity_snapshots_lookup
    ON entity_snapshots(org_id, entity_type, entity_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_snapshots_run
    ON entity_snapshots(source_run_id);

ALTER TABLE entity_snapshots ENABLE ROW LEVEL SECURITY;
