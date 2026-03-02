"""
Bright Data Indeed Job Listings Ingestion.

Accepts a list of Bright Data Indeed records and performs a batch upsert into
raw.brightdata_indeed_job_listings with ingestion batch tracking.
"""

import json
import os
from uuid import uuid4

import modal

from config import app, image

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:rVcat1Two1d8LQVE@db.ivcemmeywnlhykbuafwv.supabase.co:5432/postgres",
)


@app.function(
    image=image,
    timeout=300,
    secrets=[modal.Secret.from_name("supabase-credentials")],
)
@modal.fastapi_endpoint(method="POST")
def ingest_brightdata_indeed_jobs(records: list[dict], metadata: dict | None = None) -> dict:
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
                    (str(batch_id), "indeed", len(records), json.dumps(metadata_payload)),
                )

                upsert_rows = []
                for idx, record in enumerate(records):
                    if not isinstance(record, dict):
                        raise ValueError(f"records[{idx}] must be an object")

                    jobid = record.get("jobid")
                    if not jobid:
                        raise ValueError(f"records[{idx}].jobid is required")

                    upsert_rows.append(
                        (
                            str(batch_id),
                            str(jobid),
                            record.get("job_title"),
                            record.get("job_type"),
                            record.get("description_text"),
                            record.get("description"),
                            record.get("job_description_formatted"),
                            Json(record.get("benefits")) if record.get("benefits") is not None else None,
                            record.get("qualifications"),
                            record.get("salary_formatted"),
                            Json(record.get("shift_schedule")) if record.get("shift_schedule") is not None else None,
                            record.get("company_name"),
                            float(record["company_rating"]) if record.get("company_rating") is not None else None,
                            int(record["company_reviews_count"]) if record.get("company_reviews_count") is not None else None,
                            record.get("company_link"),
                            record.get("company_website"),
                            record.get("location"),
                            record.get("job_location"),
                            record.get("country"),
                            record.get("region"),
                            record.get("date_posted"),
                            record.get("date_posted_parsed"),
                            record.get("url"),
                            record.get("apply_link"),
                            record.get("domain"),
                            record.get("logo_url"),
                            bool(record["is_expired"]) if record.get("is_expired") is not None else None,
                            record.get("srcname"),
                            Json(record.get("discovery_input")) if record.get("discovery_input") is not None else None,
                            Json(record),
                        )
                    )

                if upsert_rows:
                    execute_values(
                        cur,
                        """
                        INSERT INTO raw.brightdata_indeed_job_listings (
                            ingestion_batch_id,
                            jobid,
                            job_title,
                            job_type,
                            description_text,
                            description,
                            job_description_formatted,
                            benefits,
                            qualifications,
                            salary_formatted,
                            shift_schedule,
                            company_name,
                            company_rating,
                            company_reviews_count,
                            company_link,
                            company_website,
                            location,
                            job_location,
                            country,
                            region,
                            date_posted,
                            date_posted_parsed,
                            url,
                            apply_link,
                            domain,
                            logo_url,
                            is_expired,
                            srcname,
                            discovery_input,
                            raw_payload
                        ) VALUES %s
                        ON CONFLICT (jobid) DO UPDATE SET
                            ingestion_batch_id = EXCLUDED.ingestion_batch_id,
                            ingested_at = now(),
                            job_title = EXCLUDED.job_title,
                            job_type = EXCLUDED.job_type,
                            description_text = EXCLUDED.description_text,
                            description = EXCLUDED.description,
                            job_description_formatted = EXCLUDED.job_description_formatted,
                            benefits = EXCLUDED.benefits,
                            qualifications = EXCLUDED.qualifications,
                            salary_formatted = EXCLUDED.salary_formatted,
                            shift_schedule = EXCLUDED.shift_schedule,
                            company_name = EXCLUDED.company_name,
                            company_rating = EXCLUDED.company_rating,
                            company_reviews_count = EXCLUDED.company_reviews_count,
                            company_link = EXCLUDED.company_link,
                            company_website = EXCLUDED.company_website,
                            location = EXCLUDED.location,
                            job_location = EXCLUDED.job_location,
                            country = EXCLUDED.country,
                            region = EXCLUDED.region,
                            date_posted = EXCLUDED.date_posted,
                            date_posted_parsed = EXCLUDED.date_posted_parsed,
                            url = EXCLUDED.url,
                            apply_link = EXCLUDED.apply_link,
                            domain = EXCLUDED.domain,
                            logo_url = EXCLUDED.logo_url,
                            is_expired = EXCLUDED.is_expired,
                            srcname = EXCLUDED.srcname,
                            discovery_input = EXCLUDED.discovery_input,
                            raw_payload = EXCLUDED.raw_payload
                        """,
                        upsert_rows,
                        page_size=500,
                    )

        return {
            "batch_id": str(batch_id),
            "records_processed": len(records),
            "source": "indeed",
        }
    finally:
        conn.close()
