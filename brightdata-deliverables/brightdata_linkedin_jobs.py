"""
Bright Data LinkedIn Job Listings Ingestion.

Accepts a list of Bright Data LinkedIn records and performs a batch upsert into
raw.brightdata_linkedin_job_listings with ingestion batch tracking.
"""

import json
import os
from datetime import datetime
from uuid import uuid4

import modal

from config import app, image

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:rVcat1Two1d8LQVE@db.ivcemmeywnlhykbuafwv.supabase.co:5432/postgres",
)


def _parse_iso_timestamptz(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@app.function(
    image=image,
    timeout=300,
    secrets=[modal.Secret.from_name("supabase-credentials")],
)
@modal.fastapi_endpoint(method="POST")
def ingest_brightdata_linkedin_jobs(records: list[dict], metadata: dict | None = None) -> dict:
    import psycopg2
    from psycopg2.extras import Json, execute_values

    if not isinstance(records, list):
        raise ValueError("records must be a list")

    batch_id = uuid4()
    metadata_payload = metadata if isinstance(metadata, dict) else {}

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO raw.brightdata_ingestion_batches (id, source, record_count, metadata)
                    VALUES (%s, %s, %s, %s::jsonb)
                    """,
                    (str(batch_id), "linkedin", len(records), json.dumps(metadata_payload)),
                )

                upsert_rows = []
                for idx, record in enumerate(records):
                    if not isinstance(record, dict):
                        raise ValueError(f"records[{idx}] must be an object")

                    job_posting_id = record.get("job_posting_id")
                    if not job_posting_id:
                        raise ValueError(f"records[{idx}].job_posting_id is required")

                    base_salary = record.get("base_salary") or {}
                    if not isinstance(base_salary, dict):
                        base_salary = {}

                    job_poster = record.get("job_poster") or {}
                    if not isinstance(job_poster, dict):
                        job_poster = {}

                    upsert_rows.append(
                        (
                            str(batch_id),
                            str(job_posting_id),
                            record.get("job_title"),
                            record.get("job_summary"),
                            record.get("job_seniority_level"),
                            record.get("job_function"),
                            record.get("job_employment_type"),
                            record.get("job_industries"),
                            record.get("job_base_pay_range"),
                            record.get("job_description_formatted"),
                            bool(record["is_easy_apply"]) if record.get("is_easy_apply") is not None else None,
                            base_salary.get("currency"),
                            float(base_salary["min_amount"]) if base_salary.get("min_amount") is not None else None,
                            float(base_salary["max_amount"]) if base_salary.get("max_amount") is not None else None,
                            base_salary.get("payment_period"),
                            record.get("salary_standards"),
                            record.get("company_name"),
                            record.get("company_id"),
                            record.get("company_url"),
                            record.get("company_logo"),
                            record.get("job_location"),
                            record.get("country_code"),
                            _parse_iso_timestamptz(record.get("job_posted_date")),
                            record.get("job_posted_time"),
                            record.get("url"),
                            record.get("apply_link"),
                            int(record["job_num_applicants"]) if record.get("job_num_applicants") is not None else None,
                            job_poster.get("name"),
                            job_poster.get("title"),
                            job_poster.get("url"),
                            bool(record["application_availability"]) if record.get("application_availability") is not None else None,
                            record.get("title_id"),
                            Json(record.get("discovery_input")) if record.get("discovery_input") is not None else None,
                            Json(record),
                        )
                    )

                if upsert_rows:
                    execute_values(
                        cur,
                        """
                        INSERT INTO raw.brightdata_linkedin_job_listings (
                            ingestion_batch_id,
                            job_posting_id,
                            job_title,
                            job_summary,
                            job_seniority_level,
                            job_function,
                            job_employment_type,
                            job_industries,
                            job_base_pay_range,
                            job_description_formatted,
                            is_easy_apply,
                            base_salary_currency,
                            base_salary_min_amount,
                            base_salary_max_amount,
                            base_salary_payment_period,
                            salary_standards,
                            company_name,
                            company_id,
                            company_url,
                            company_logo,
                            job_location,
                            country_code,
                            job_posted_date,
                            job_posted_time,
                            url,
                            apply_link,
                            job_num_applicants,
                            job_poster_name,
                            job_poster_title,
                            job_poster_url,
                            application_availability,
                            title_id,
                            discovery_input,
                            raw_payload
                        ) VALUES %s
                        ON CONFLICT (job_posting_id) DO UPDATE SET
                            ingestion_batch_id = EXCLUDED.ingestion_batch_id,
                            ingested_at = now(),
                            job_title = EXCLUDED.job_title,
                            job_summary = EXCLUDED.job_summary,
                            job_seniority_level = EXCLUDED.job_seniority_level,
                            job_function = EXCLUDED.job_function,
                            job_employment_type = EXCLUDED.job_employment_type,
                            job_industries = EXCLUDED.job_industries,
                            job_base_pay_range = EXCLUDED.job_base_pay_range,
                            job_description_formatted = EXCLUDED.job_description_formatted,
                            is_easy_apply = EXCLUDED.is_easy_apply,
                            base_salary_currency = EXCLUDED.base_salary_currency,
                            base_salary_min_amount = EXCLUDED.base_salary_min_amount,
                            base_salary_max_amount = EXCLUDED.base_salary_max_amount,
                            base_salary_payment_period = EXCLUDED.base_salary_payment_period,
                            salary_standards = EXCLUDED.salary_standards,
                            company_name = EXCLUDED.company_name,
                            company_id = EXCLUDED.company_id,
                            company_url = EXCLUDED.company_url,
                            company_logo = EXCLUDED.company_logo,
                            job_location = EXCLUDED.job_location,
                            country_code = EXCLUDED.country_code,
                            job_posted_date = EXCLUDED.job_posted_date,
                            job_posted_time = EXCLUDED.job_posted_time,
                            url = EXCLUDED.url,
                            apply_link = EXCLUDED.apply_link,
                            job_num_applicants = EXCLUDED.job_num_applicants,
                            job_poster_name = EXCLUDED.job_poster_name,
                            job_poster_title = EXCLUDED.job_poster_title,
                            job_poster_url = EXCLUDED.job_poster_url,
                            application_availability = EXCLUDED.application_availability,
                            title_id = EXCLUDED.title_id,
                            discovery_input = EXCLUDED.discovery_input,
                            raw_payload = EXCLUDED.raw_payload
                        """,
                        upsert_rows,
                        page_size=500,
                    )

        return {
            "batch_id": str(batch_id),
            "records_processed": len(records),
            "source": "linkedin",
        }
    finally:
        conn.close()
