-- 005_operation_execution_history.sql — durable operation execution logs

CREATE TABLE IF NOT EXISTS operation_runs (
    run_id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    role TEXT NOT NULL,
    auth_method TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person')),
    status TEXT NOT NULL CHECK (status IN ('found', 'not_found', 'failed', 'verified')),
    missing_inputs JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_payload JSONB NOT NULL,
    output_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operation_runs_org_created_at
    ON operation_runs(org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_operation_runs_operation_created_at
    ON operation_runs(operation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_operation_runs_status_created_at
    ON operation_runs(status, created_at DESC);

CREATE TABLE IF NOT EXISTS operation_attempts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id UUID NOT NULL REFERENCES operation_runs(run_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('found', 'not_found', 'failed', 'verified', 'skipped')),
    skip_reason TEXT,
    http_status INT,
    provider_status TEXT,
    duration_ms INT CHECK (duration_ms >= 0),
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operation_attempts_run_id
    ON operation_attempts(run_id);
CREATE INDEX IF NOT EXISTS idx_operation_attempts_provider_created_at
    ON operation_attempts(provider, created_at DESC);

CREATE TRIGGER update_operation_runs_updated_at
    BEFORE UPDATE ON operation_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE operation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE operation_attempts ENABLE ROW LEVEL SECURITY;

