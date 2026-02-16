-- 001_initial_schema.sql — Foundation schema for data-engine-x-api

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";

-- Enums
CREATE TYPE user_role AS ENUM ('org_admin', 'company_admin', 'member');
CREATE TYPE step_type AS ENUM ('clean', 'enrich', 'analyze', 'extract', 'transform');
CREATE TYPE run_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'canceled');
CREATE TYPE step_status AS ENUM ('queued', 'running', 'succeeded', 'failed', 'skipped', 'retrying');
CREATE TYPE submission_status AS ENUM ('received', 'validated', 'queued', 'running', 'completed', 'failed', 'canceled');

-- Tenancy roots
CREATE TABLE orgs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    external_ref TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_companies_org_name UNIQUE (org_id, name),
    CONSTRAINT uq_companies_id_org UNIQUE (id, org_id)
);

CREATE UNIQUE INDEX uq_companies_org_external_ref
    ON companies (org_id, external_ref)
    WHERE external_ref IS NOT NULL;
CREATE INDEX idx_companies_org_id ON companies(org_id);

-- Users and machine auth
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
    email CITEXT NOT NULL UNIQUE,
    full_name TEXT,
    role user_role NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_org_id ON users(org_id);
CREATE INDEX idx_users_company_id ON users(company_id);
CREATE INDEX idx_users_role ON users(role);

CREATE TABLE api_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    role user_role NOT NULL,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_api_tokens_org_id ON api_tokens(org_id);
CREATE INDEX idx_api_tokens_company_id ON api_tokens(company_id);
CREATE INDEX idx_api_tokens_role ON api_tokens(role);
CREATE INDEX idx_api_tokens_revoked_at ON api_tokens(revoked_at);

-- Platform-level auth (not tenant-scoped)
CREATE TABLE super_admins (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email CITEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Step registry (global)
CREATE TABLE steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    step_type step_type NOT NULL,
    default_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    input_schema JSONB,
    output_schema JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_steps_step_type ON steps(step_type);
CREATE INDEX idx_steps_is_active ON steps(is_active);
CREATE INDEX idx_steps_slug ON steps(slug);

-- Org-scoped execution blueprint
CREATE TABLE blueprints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_blueprints_org_name UNIQUE (org_id, name),
    CONSTRAINT uq_blueprints_id_org UNIQUE (id, org_id)
);

CREATE INDEX idx_blueprints_org_id ON blueprints(org_id);
CREATE INDEX idx_blueprints_is_active ON blueprints(is_active);

CREATE TABLE blueprint_steps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    blueprint_id UUID NOT NULL REFERENCES blueprints(id) ON DELETE CASCADE,
    step_id UUID NOT NULL REFERENCES steps(id) ON DELETE RESTRICT,
    position INT NOT NULL CHECK (position > 0),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_blueprint_steps_position UNIQUE (blueprint_id, position)
);

CREATE INDEX idx_blueprint_steps_blueprint_id ON blueprint_steps(blueprint_id);
CREATE INDEX idx_blueprint_steps_step_id ON blueprint_steps(step_id);

-- Submissions and runs
CREATE TABLE submissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    blueprint_id UUID NOT NULL REFERENCES blueprints(id) ON DELETE RESTRICT,
    submitted_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    source TEXT,
    input_payload JSONB NOT NULL,
    status submission_status NOT NULL DEFAULT 'received',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_submissions_id_org UNIQUE (id, org_id)
);

CREATE INDEX idx_submissions_org_id ON submissions(org_id);
CREATE INDEX idx_submissions_company_id ON submissions(company_id);
CREATE INDEX idx_submissions_blueprint_id ON submissions(blueprint_id);
CREATE INDEX idx_submissions_status_created_at ON submissions(status, created_at DESC);

CREATE TABLE pipeline_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    blueprint_id UUID NOT NULL REFERENCES blueprints(id) ON DELETE RESTRICT,
    trigger_run_id TEXT UNIQUE,
    blueprint_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    blueprint_version INT NOT NULL DEFAULT 1 CHECK (blueprint_version > 0),
    status run_status NOT NULL DEFAULT 'queued',
    attempt INT NOT NULL DEFAULT 1 CHECK (attempt > 0),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    error_message TEXT,
    error_details JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pipeline_runs_id_org UNIQUE (id, org_id)
);

CREATE INDEX idx_pipeline_runs_org_created_at ON pipeline_runs(org_id, created_at DESC);
CREATE INDEX idx_pipeline_runs_submission_id ON pipeline_runs(submission_id);
CREATE INDEX idx_pipeline_runs_status_created_at ON pipeline_runs(status, created_at DESC);
CREATE INDEX idx_pipeline_runs_blueprint_id ON pipeline_runs(blueprint_id);

CREATE TABLE step_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    pipeline_run_id UUID NOT NULL REFERENCES pipeline_runs(id) ON DELETE CASCADE,
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    step_id UUID NOT NULL REFERENCES steps(id) ON DELETE RESTRICT,
    blueprint_step_id UUID REFERENCES blueprint_steps(id) ON DELETE SET NULL,
    step_position INT NOT NULL CHECK (step_position > 0),
    task_run_id TEXT,
    status step_status NOT NULL DEFAULT 'queued',
    input_payload JSONB,
    output_payload JSONB,
    error_message TEXT,
    error_details JSONB,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    duration_ms INT CHECK (duration_ms >= 0),
    attempt INT NOT NULL DEFAULT 1 CHECK (attempt > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_step_results_run_position_attempt UNIQUE (pipeline_run_id, step_position, attempt)
);

CREATE INDEX idx_step_results_org_created_at ON step_results(org_id, created_at DESC);
CREATE INDEX idx_step_results_pipeline_position ON step_results(pipeline_run_id, step_position);
CREATE INDEX idx_step_results_status_created_at ON step_results(status, created_at DESC);
CREATE INDEX idx_step_results_submission_id ON step_results(submission_id);

-- Cross-table tenancy integrity checks
CREATE OR REPLACE FUNCTION enforce_tenant_integrity()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_TABLE_NAME = 'users' OR TG_TABLE_NAME = 'api_tokens' THEN
        IF NEW.company_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION '% company_id does not belong to org_id', TG_TABLE_NAME;
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'submissions' THEN
        IF NOT EXISTS (
            SELECT 1 FROM companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'submission company_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM blueprints b WHERE b.id = NEW.blueprint_id AND b.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'submission blueprint_id does not belong to org_id';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'pipeline_runs' THEN
        IF NOT EXISTS (
            SELECT 1 FROM submissions s WHERE s.id = NEW.submission_id AND s.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'pipeline_run submission_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'pipeline_run company_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM blueprints b WHERE b.id = NEW.blueprint_id AND b.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'pipeline_run blueprint_id does not belong to org_id';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'step_results' THEN
        IF NOT EXISTS (
            SELECT 1 FROM pipeline_runs pr WHERE pr.id = NEW.pipeline_run_id AND pr.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'step_result pipeline_run_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM submissions s WHERE s.id = NEW.submission_id AND s.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'step_result submission_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'step_result company_id does not belong to org_id';
        END IF;
        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER enforce_users_tenant_integrity
    BEFORE INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION enforce_tenant_integrity();

CREATE TRIGGER enforce_api_tokens_tenant_integrity
    BEFORE INSERT OR UPDATE ON api_tokens
    FOR EACH ROW EXECUTE FUNCTION enforce_tenant_integrity();

CREATE TRIGGER enforce_submissions_tenant_integrity
    BEFORE INSERT OR UPDATE ON submissions
    FOR EACH ROW EXECUTE FUNCTION enforce_tenant_integrity();

CREATE TRIGGER enforce_pipeline_runs_tenant_integrity
    BEFORE INSERT OR UPDATE ON pipeline_runs
    FOR EACH ROW EXECUTE FUNCTION enforce_tenant_integrity();

CREATE TRIGGER enforce_step_results_tenant_integrity
    BEFORE INSERT OR UPDATE ON step_results
    FOR EACH ROW EXECUTE FUNCTION enforce_tenant_integrity();

-- updated_at support
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_orgs_updated_at
    BEFORE UPDATE ON orgs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_api_tokens_updated_at
    BEFORE UPDATE ON api_tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_super_admins_updated_at
    BEFORE UPDATE ON super_admins
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_steps_updated_at
    BEFORE UPDATE ON steps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_blueprints_updated_at
    BEFORE UPDATE ON blueprints
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_blueprint_steps_updated_at
    BEFORE UPDATE ON blueprint_steps
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_submissions_updated_at
    BEFORE UPDATE ON submissions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_pipeline_runs_updated_at
    BEFORE UPDATE ON pipeline_runs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_step_results_updated_at
    BEFORE UPDATE ON step_results
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS enablement only (policies intentionally deferred)
ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE blueprints ENABLE ROW LEVEL SECURITY;
ALTER TABLE blueprint_steps ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE step_results ENABLE ROW LEVEL SECURITY;
