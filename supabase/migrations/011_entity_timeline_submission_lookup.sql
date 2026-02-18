-- 011_entity_timeline_submission_lookup.sql
-- Adds submission-level investigation index for entity timeline.

CREATE INDEX IF NOT EXISTS idx_entity_timeline_submission_lookup
    ON entity_timeline(org_id, submission_id, created_at DESC);
