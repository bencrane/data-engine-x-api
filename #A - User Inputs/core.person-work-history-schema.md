create table core.person_work_history (
  id uuid not null default gen_random_uuid (),
  linkedin_url text null,
  company_domain text null,
  company_name text null,
  company_linkedin_url text null,
  title text null,
  matched_job_function text null,
  matched_seniority text null,
  start_date date null,
  end_date date null,
  is_current boolean null,
  experience_order integer null,
  source_id uuid null,
  created_at timestamp with time zone null default now(),
  linkedin_url_type text null default 'real'::text,
  resolved_company_domain text null,
  matched_cleaned_job_title text null,
  last_verified_at timestamp with time zone null,
  linkedin_salesnav_url text null,
  matched_company_domain text null,
  matched_company_linkedin_url text null,
  experience_key text null,
  constraint person_work_history_pkey primary key (id)
) TABLESPACE pg_default;

create index IF not exists idx_pwh_linkedin_url on core.person_work_history using btree (linkedin_url) TABLESPACE pg_default;

create index IF not exists idx_pwh_company_domain on core.person_work_history using btree (company_domain) TABLESPACE pg_default;

create index IF not exists idx_pwh_linkedin_salesnav_url on core.person_work_history using btree (linkedin_salesnav_url) TABLESPACE pg_default;

create index IF not exists idx_pwh_norm_company_unmatched on core.person_work_history using btree (
  lower(
    TRIM(
      both
      from
        company_name
    )
  )
) TABLESPACE pg_default
where
  (
    (matched_company_domain is null)
    and (company_name is not null)
  );

create index IF not exists idx_pwh_is_current on core.person_work_history using btree (is_current) TABLESPACE pg_default;

create index IF not exists idx_pwh_start_date on core.person_work_history using btree (start_date) TABLESPACE pg_default;