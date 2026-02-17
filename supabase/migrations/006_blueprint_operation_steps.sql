-- 006_blueprint_operation_steps.sql
-- Add operation-native blueprint step fields while preserving legacy columns.

ALTER TABLE blueprint_steps
    ADD COLUMN IF NOT EXISTS operation_id TEXT,
    ADD COLUMN IF NOT EXISTS step_config JSONB;

-- Allow operation-native rows that do not reference legacy step registry rows.
ALTER TABLE blueprint_steps
    ALTER COLUMN step_id DROP NOT NULL;

-- step_results also needs to support operation-native rows without legacy step_id.
ALTER TABLE step_results
    ALTER COLUMN step_id DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_blueprint_steps_operation_id
    ON blueprint_steps(operation_id);
