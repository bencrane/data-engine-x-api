create table extracted.person_experience (
  id uuid not null default gen_random_uuid (),
  raw_payload_id uuid not null,
  linkedin_url text not null,
  company text null,
  company_domain text null,
  company_linkedin_url text null,
  company_org_id bigint null,
  title text null,
  summary text null,
  locality text null,
  start_date date null,
  end_date date null,
  is_current boolean null,
  experience_order integer null,
  created_at timestamp with time zone null default now(),
  matched_cleaned_job_title text null,
  matched_job_function text null,
  matched_seniority text null,
  matched_company_domain text null,
  constraint person_experience_pkey primary key (id),
  constraint person_experience_raw_payload_id_fkey foreign KEY (raw_payload_id) references raw.person_payloads (id)
) TABLESPACE pg_default;

create index IF not exists idx_person_experience_linkedin_url on extracted.person_experience using btree (linkedin_url) TABLESPACE pg_default;

create index IF not exists idx_person_experience_company_domain on extracted.person_experience using btree (company_domain) TABLESPACE pg_default;

create index IF not exists idx_person_experience_company_org_id on extracted.person_experience using btree (company_org_id) TABLESPACE pg_default;

create index IF not exists idx_pe_matchable_company_clean on extracted.person_experience using btree (
  lower(
    TRIM(
      both
      from
        company
    )
  ),
  id
) TABLESPACE pg_default
where
  (
    (company_domain is null)
    and (matched_company_domain is null)
    and (company is not null)
  );

create trigger trg_sync_person_experience
after INSERT on extracted.person_experience for EACH row
execute FUNCTION sync_person_experience_to_core ();