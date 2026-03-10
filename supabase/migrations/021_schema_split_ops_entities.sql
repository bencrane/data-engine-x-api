BEGIN;

DO $$
DECLARE
    required_table TEXT;
    required_tables TEXT[] := ARRAY[
        'orgs',
        'companies',
        'users',
        'api_tokens',
        'super_admins',
        'steps',
        'blueprints',
        'blueprint_steps',
        'submissions',
        'pipeline_runs',
        'step_results',
        'operation_runs',
        'operation_attempts',
        'company_entities',
        'person_entities',
        'job_posting_entities',
        'entity_timeline',
        'entity_snapshots',
        'entity_relationships',
        'icp_job_titles',
        'extracted_icp_job_title_details',
        'company_intel_briefings',
        'person_intel_briefings',
        'gemini_icp_job_titles',
        'company_customers',
        'company_ads',
        'salesnav_prospects'
    ];
BEGIN
    FOREACH required_table IN ARRAY required_tables LOOP
        IF to_regclass(format('public.%I', required_table)) IS NULL THEN
            RAISE EXCEPTION
                'Schema split requires public.% to exist before migration 021 runs',
                required_table;
        END IF;
    END LOOP;
END $$;

CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS entities;

ALTER TABLE public.orgs SET SCHEMA ops;
ALTER TABLE public.companies SET SCHEMA ops;
ALTER TABLE public.users SET SCHEMA ops;
ALTER TABLE public.api_tokens SET SCHEMA ops;
ALTER TABLE public.super_admins SET SCHEMA ops;
ALTER TABLE public.steps SET SCHEMA ops;
ALTER TABLE public.blueprints SET SCHEMA ops;
ALTER TABLE public.blueprint_steps SET SCHEMA ops;
ALTER TABLE public.submissions SET SCHEMA ops;
ALTER TABLE public.pipeline_runs SET SCHEMA ops;
ALTER TABLE public.step_results SET SCHEMA ops;
ALTER TABLE public.operation_runs SET SCHEMA ops;
ALTER TABLE public.operation_attempts SET SCHEMA ops;

ALTER TABLE public.company_entities SET SCHEMA entities;
ALTER TABLE public.person_entities SET SCHEMA entities;
ALTER TABLE public.job_posting_entities SET SCHEMA entities;
ALTER TABLE public.entity_timeline SET SCHEMA entities;
ALTER TABLE public.entity_snapshots SET SCHEMA entities;
ALTER TABLE public.entity_relationships SET SCHEMA entities;
ALTER TABLE public.icp_job_titles SET SCHEMA entities;
ALTER TABLE public.extracted_icp_job_title_details SET SCHEMA entities;
ALTER TABLE public.company_intel_briefings SET SCHEMA entities;
ALTER TABLE public.person_intel_briefings SET SCHEMA entities;
ALTER TABLE public.gemini_icp_job_titles SET SCHEMA entities;
ALTER TABLE public.company_customers SET SCHEMA entities;
ALTER TABLE public.company_ads SET SCHEMA entities;
ALTER TABLE public.salesnav_prospects SET SCHEMA entities;

CREATE OR REPLACE FUNCTION public.enforce_tenant_integrity()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_TABLE_NAME = 'users' OR TG_TABLE_NAME = 'api_tokens' THEN
        IF NEW.company_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM ops.companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION '% company_id does not belong to org_id', TG_TABLE_NAME;
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'submissions' THEN
        IF NOT EXISTS (
            SELECT 1 FROM ops.companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'submission company_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM ops.blueprints b WHERE b.id = NEW.blueprint_id AND b.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'submission blueprint_id does not belong to org_id';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'pipeline_runs' THEN
        IF NOT EXISTS (
            SELECT 1 FROM ops.submissions s WHERE s.id = NEW.submission_id AND s.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'pipeline_run submission_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM ops.companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'pipeline_run company_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM ops.blueprints b WHERE b.id = NEW.blueprint_id AND b.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'pipeline_run blueprint_id does not belong to org_id';
        END IF;
        RETURN NEW;
    END IF;

    IF TG_TABLE_NAME = 'step_results' THEN
        IF NOT EXISTS (
            SELECT 1 FROM ops.pipeline_runs pr WHERE pr.id = NEW.pipeline_run_id AND pr.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'step_result pipeline_run_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM ops.submissions s WHERE s.id = NEW.submission_id AND s.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'step_result submission_id does not belong to org_id';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM ops.companies c WHERE c.id = NEW.company_id AND c.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'step_result company_id does not belong to org_id';
        END IF;
        RETURN NEW;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMIT;
