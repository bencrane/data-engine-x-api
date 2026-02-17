-- 010_fan_out.sql
-- Add parent/child pipeline lineage and fan-out step metadata.

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS parent_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL;

ALTER TABLE blueprint_steps
    ADD COLUMN IF NOT EXISTS fan_out BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_parent_pipeline_run_id
    ON pipeline_runs(parent_pipeline_run_id);
