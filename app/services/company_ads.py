from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.database import get_supabase_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _clean_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "active"}:
            return True
        if lowered in {"false", "0", "no", "inactive"}:
            return False
    return None


def _first_non_empty(raw_ad: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in raw_ad and raw_ad[key] is not None:
            value = raw_ad[key]
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    return cleaned
                continue
            return value
    return None


def _normalize_company_domain(company_domain: str) -> str:
    candidate = company_domain.strip().lower()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    netloc = parsed.netloc or parsed.path
    normalized = netloc.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized.rstrip("/")


def _extract_ad_fields(raw_ad: dict[str, Any], platform: str) -> dict[str, Any]:
    normalized_platform = platform.strip().lower()

    ad_id_candidates: list[str] = ["ad_id", "id", "adid", "ad_archive_id", "archive_id"]
    if normalized_platform == "linkedin":
        ad_id_candidates = [
            "ad_id",
            "creative_id",
            "sponsored_content_id",
            "id",
            "urn",
            "page_ad_id",
        ]
    elif normalized_platform == "meta":
        ad_id_candidates = [
            "ad_archive_id",
            "id",
            "ad_id",
            "archive_id",
            "adArchiveID",
        ]
    elif normalized_platform == "google":
        ad_id_candidates = [
            "ad_id",
            "adId",
            "creative_id",
            "asset_id",
            "id",
        ]

    ad_id = _clean_text(_first_non_empty(raw_ad, ad_id_candidates))
    headline = _clean_text(
        _first_non_empty(raw_ad, ["headline", "title", "ad_title", "primary_text_headline"])
    )
    body_text = _clean_text(
        _first_non_empty(raw_ad, ["body", "description", "text", "ad_body", "primary_text"])
    )
    cta_text = _clean_text(
        _first_non_empty(raw_ad, ["cta", "call_to_action", "cta_text", "callToAction"])
    )
    landing_page_url = _clean_text(
        _first_non_empty(
            raw_ad,
            ["landing_page", "destination_url", "landing_page_url", "link_url", "final_url"],
        )
    )
    media_url = _clean_text(
        _first_non_empty(
            raw_ad,
            ["image_url", "video_url", "media_url", "thumbnail_url", "creative_url", "asset_url"],
        )
    )

    return {
        "ad_id": ad_id,
        "ad_type": _clean_text(_first_non_empty(raw_ad, ["ad_type", "type"])),
        "ad_format": _clean_text(_first_non_empty(raw_ad, ["ad_format", "format"])),
        "headline": headline,
        "body_text": body_text,
        "cta_text": cta_text,
        "landing_page_url": landing_page_url,
        "media_url": media_url,
        "media_type": _clean_text(_first_non_empty(raw_ad, ["media_type", "type_of_media"])),
        "advertiser_name": _clean_text(
            _first_non_empty(raw_ad, ["advertiser_name", "page_name", "account_name", "company_name"])
        ),
        "advertiser_url": _clean_text(
            _first_non_empty(raw_ad, ["advertiser_url", "page_url", "account_url", "company_url"])
        ),
        "start_date": _clean_text(_first_non_empty(raw_ad, ["start_date", "ad_start_date", "start_time"])),
        "end_date": _clean_text(_first_non_empty(raw_ad, ["end_date", "ad_end_date", "end_time"])),
        "is_active": _clean_bool(_first_non_empty(raw_ad, ["is_active", "active", "status"])),
        "impressions_range": _clean_text(
            _first_non_empty(raw_ad, ["impressions_range", "impressions", "impression_range"])
        ),
        "spend_range": _clean_text(_first_non_empty(raw_ad, ["spend_range", "spend", "spend_estimate"])),
        "country_code": _clean_text(_first_non_empty(raw_ad, ["country_code", "country"])),
    }


def upsert_company_ads(
    *,
    org_id: str,
    company_domain: str,
    company_entity_id: str | None = None,
    platform: str,
    ads: list[dict[str, Any]],
    discovered_by_operation_id: str,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    normalized_company_domain = _normalize_company_domain(company_domain)
    normalized_platform = platform.strip().lower()
    now = _utc_now_iso()

    rows_with_ad_id: list[dict[str, Any]] = []
    rows_without_ad_id: list[dict[str, Any]] = []

    for ad in ads:
        if not isinstance(ad, dict):
            continue

        extracted = _extract_ad_fields(ad, normalized_platform)
        row = {
            "org_id": org_id,
            "company_domain": normalized_company_domain,
            "company_entity_id": company_entity_id,
            "platform": normalized_platform,
            "raw_ad": ad,
            "discovered_by_operation_id": discovered_by_operation_id,
            "source_submission_id": source_submission_id,
            "source_pipeline_run_id": source_pipeline_run_id,
            "updated_at": now,
            **extracted,
        }

        if row["ad_id"]:
            rows_with_ad_id.append(row)
        else:
            rows_without_ad_id.append(row)

    persisted_rows: list[dict[str, Any]] = []
    client = get_supabase_client().table("company_ads")

    if rows_with_ad_id:
        upsert_result = client.upsert(
            rows_with_ad_id,
            on_conflict="org_id,company_domain,platform,ad_id",
        ).execute()
        persisted_rows.extend(upsert_result.data or [])

    if rows_without_ad_id:
        insert_result = client.insert(rows_without_ad_id).execute()
        persisted_rows.extend(insert_result.data or [])

    return persisted_rows


def query_company_ads(
    *,
    org_id: str,
    company_domain: str | None = None,
    company_entity_id: str | None = None,
    platform: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("company_ads").select("*").eq("org_id", org_id)
    if company_domain:
        query = query.eq("company_domain", _normalize_company_domain(company_domain))
    if company_entity_id:
        query = query.eq("company_entity_id", company_entity_id)
    if platform:
        query = query.eq("platform", platform.strip().lower())

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
