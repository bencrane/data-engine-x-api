BEGIN;

CREATE TABLE IF NOT EXISTS ops.company_blueprint_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    company_id UUID NOT NULL,
    blueprint_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id UUID,
    updated_by_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_blueprint_configs_org_company_name UNIQUE (org_id, company_id, name),
    CONSTRAINT uq_company_blueprint_configs_id_org_company UNIQUE (id, org_id, company_id),
    CONSTRAINT fk_company_blueprint_configs_company FOREIGN KEY (company_id, org_id)
        REFERENCES ops.companies(id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_company_blueprint_configs_blueprint FOREIGN KEY (blueprint_id, org_id)
        REFERENCES ops.blueprints(id, org_id)
        ON DELETE RESTRICT,
    CONSTRAINT fk_company_blueprint_configs_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES ops.users(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_company_blueprint_configs_updated_by FOREIGN KEY (updated_by_user_id)
        REFERENCES ops.users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_company_blueprint_configs_org_company
    ON ops.company_blueprint_configs(org_id, company_id);
CREATE INDEX IF NOT EXISTS idx_company_blueprint_configs_blueprint
    ON ops.company_blueprint_configs(blueprint_id);
CREATE INDEX IF NOT EXISTS idx_company_blueprint_configs_is_active
    ON ops.company_blueprint_configs(is_active);

CREATE TABLE IF NOT EXISTS ops.company_blueprint_schedules (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    company_id UUID NOT NULL,
    config_id UUID NOT NULL,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    cadence_minutes INT NOT NULL CHECK (cadence_minutes > 0),
    next_run_at TIMESTAMPTZ NOT NULL,
    last_claimed_at TIMESTAMPTZ,
    last_succeeded_at TIMESTAMPTZ,
    last_failed_at TIMESTAMPTZ,
    last_submission_id UUID,
    last_error TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id UUID,
    updated_by_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_blueprint_schedules_org_company_name UNIQUE (org_id, company_id, name),
    CONSTRAINT uq_company_blueprint_schedules_id_org_company UNIQUE (id, org_id, company_id),
    CONSTRAINT fk_company_blueprint_schedules_config FOREIGN KEY (config_id, org_id, company_id)
        REFERENCES ops.company_blueprint_configs(id, org_id, company_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_company_blueprint_schedules_company FOREIGN KEY (company_id, org_id)
        REFERENCES ops.companies(id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_company_blueprint_schedules_last_submission FOREIGN KEY (last_submission_id)
        REFERENCES ops.submissions(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_company_blueprint_schedules_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES ops.users(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_company_blueprint_schedules_updated_by FOREIGN KEY (updated_by_user_id)
        REFERENCES ops.users(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_company_blueprint_schedules_due
    ON ops.company_blueprint_schedules(is_active, next_run_at);
CREATE INDEX IF NOT EXISTS idx_company_blueprint_schedules_org_company
    ON ops.company_blueprint_schedules(org_id, company_id);
CREATE INDEX IF NOT EXISTS idx_company_blueprint_schedules_config
    ON ops.company_blueprint_schedules(config_id);

CREATE TABLE IF NOT EXISTS ops.company_blueprint_schedule_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    company_id UUID NOT NULL,
    config_id UUID NOT NULL,
    schedule_id UUID NOT NULL,
    scheduled_for TIMESTAMPTZ NOT NULL,
    scheduler_task_id TEXT,
    scheduler_invoked_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'claimed' CHECK (status IN ('claimed', 'running', 'succeeded', 'failed', 'skipped')),
    submission_id UUID,
    pipeline_run_id UUID,
    error_message TEXT,
    error_details JSONB,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_blueprint_schedule_runs_fire_window UNIQUE (schedule_id, scheduled_for),
    CONSTRAINT fk_company_blueprint_schedule_runs_schedule FOREIGN KEY (schedule_id, org_id, company_id)
        REFERENCES ops.company_blueprint_schedules(id, org_id, company_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_company_blueprint_schedule_runs_config FOREIGN KEY (config_id, org_id, company_id)
        REFERENCES ops.company_blueprint_configs(id, org_id, company_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_company_blueprint_schedule_runs_submission FOREIGN KEY (submission_id)
        REFERENCES ops.submissions(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_company_blueprint_schedule_runs_pipeline_run FOREIGN KEY (pipeline_run_id)
        REFERENCES ops.pipeline_runs(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_company_blueprint_schedule_runs_schedule
    ON ops.company_blueprint_schedule_runs(schedule_id, scheduled_for DESC);
CREATE INDEX IF NOT EXISTS idx_company_blueprint_schedule_runs_status
    ON ops.company_blueprint_schedule_runs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_blueprint_schedule_runs_org_company
    ON ops.company_blueprint_schedule_runs(org_id, company_id);

CREATE TABLE IF NOT EXISTS ops.company_entity_associations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    company_id UUID NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person', 'job')),
    entity_id UUID NOT NULL,
    source_submission_id UUID,
    source_pipeline_run_id UUID,
    source_step_result_id UUID,
    source_operation_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_company_entity_associations UNIQUE (org_id, company_id, entity_type, entity_id),
    CONSTRAINT fk_company_entity_associations_company FOREIGN KEY (company_id, org_id)
        REFERENCES ops.companies(id, org_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_company_entity_associations_submission FOREIGN KEY (source_submission_id)
        REFERENCES ops.submissions(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_company_entity_associations_pipeline_run FOREIGN KEY (source_pipeline_run_id)
        REFERENCES ops.pipeline_runs(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_company_entity_associations_step_result FOREIGN KEY (source_step_result_id)
        REFERENCES ops.step_results(id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_company_entity_associations_entity_lookup
    ON ops.company_entity_associations(org_id, company_id, entity_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_entity_associations_entity_id
    ON ops.company_entity_associations(entity_type, entity_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_submissions_client_automation_schedule_run
    ON ops.submissions ((metadata->>'schedule_run_id'))
    WHERE source = 'client_automation_schedule'
      AND (metadata->>'schedule_run_id') IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column') THEN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'update_company_blueprint_configs_updated_at'
        ) THEN
            CREATE TRIGGER update_company_blueprint_configs_updated_at
                BEFORE UPDATE ON ops.company_blueprint_configs
                FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'update_company_blueprint_schedules_updated_at'
        ) THEN
            CREATE TRIGGER update_company_blueprint_schedules_updated_at
                BEFORE UPDATE ON ops.company_blueprint_schedules
                FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'update_company_blueprint_schedule_runs_updated_at'
        ) THEN
            CREATE TRIGGER update_company_blueprint_schedule_runs_updated_at
                BEFORE UPDATE ON ops.company_blueprint_schedule_runs
                FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgname = 'update_company_entity_associations_updated_at'
        ) THEN
            CREATE TRIGGER update_company_entity_associations_updated_at
                BEFORE UPDATE ON ops.company_entity_associations
                FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
        END IF;
    END IF;
END $$;

COMMIT;
