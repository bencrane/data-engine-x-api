-- 014_entity_relationships.sql
-- Typed, directional relationships between entities (companies and persons).

CREATE TABLE IF NOT EXISTS entity_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,

    -- Source entity
    source_entity_type TEXT NOT NULL CHECK (source_entity_type IN ('company', 'person')),
    source_entity_id UUID,
    source_identifier TEXT NOT NULL,

    -- Relationship
    relationship TEXT NOT NULL,

    -- Target entity
    target_entity_type TEXT NOT NULL CHECK (target_entity_type IN ('company', 'person')),
    target_entity_id UUID,
    target_identifier TEXT NOT NULL,

    -- Context
    metadata JSONB DEFAULT '{}',
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    source_operation_id TEXT,

    -- Lifecycle
    valid_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup constraint: same relationship between same entities is recorded once
CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_relationships_dedup
    ON entity_relationships(org_id, source_identifier, relationship, target_identifier);

-- Query patterns
CREATE INDEX IF NOT EXISTS idx_entity_relationships_source
    ON entity_relationships(org_id, source_identifier, relationship);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_target
    ON entity_relationships(org_id, target_identifier, relationship);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_type
    ON entity_relationships(org_id, relationship);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_submission
    ON entity_relationships(org_id, source_submission_id);

DROP TRIGGER IF EXISTS update_entity_relationships_updated_at ON entity_relationships;
CREATE TRIGGER update_entity_relationships_updated_at
    BEFORE UPDATE ON entity_relationships
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entity_relationships ENABLE ROW LEVEL SECURITY;
