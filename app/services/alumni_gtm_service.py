from __future__ import annotations

from datetime import date, datetime, timezone
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from app.database import get_supabase_client
from app.models.alumni_gtm import (
    AlumniGtmAds,
    AlumniGtmCurrentCompany,
    AlumniGtmFirmographics,
    AlumniGtmLead,
    AlumniGtmLeadsResponse,
    AlumniGtmPerson,
    AlumniGtmPriorCompany,
    AlumniGtmPriorCompanySummary,
    AlumniGtmStoreleads,
)

_CACHE_TTL_SECONDS = 300
_CACHE_MAX_ITEMS = 200
_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
_cache_lock = Lock()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_domain(domain: str) -> str:
    candidate = domain.strip().lower()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    normalized = (parsed.netloc or parsed.path).strip().lower().rstrip("/")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _table(schema_name: str, table_name: str):
    return get_supabase_client().schema(schema_name).table(table_name)


def _to_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _cache_key(
    *,
    origin_company_domain: str,
    gtm_fit: bool | None,
    prior_company_domain: str | None,
    limit: int,
    offset: int,
) -> str:
    return "|".join(
        [
            origin_company_domain,
            str(gtm_fit),
            prior_company_domain or "",
            str(limit),
            str(offset),
        ]
    )


def _get_cached_response(key: str) -> AlumniGtmLeadsResponse | None:
    with _cache_lock:
        cached = _cache.get(key)
        if cached is None:
            return None
        cached_at, payload = cached
        if (_now_utc() - cached_at).total_seconds() > _CACHE_TTL_SECONDS:
            _cache.pop(key, None)
            return None
    return AlumniGtmLeadsResponse.model_validate(payload)


def _set_cached_response(key: str, response: AlumniGtmLeadsResponse) -> None:
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX_ITEMS:
            oldest_key = min(_cache.items(), key=lambda item: item[1][0])[0]
            _cache.pop(oldest_key, None)
        _cache[key] = (_now_utc(), response.model_dump(mode="json"))


def _resolve_best_work_history(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    best_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        linkedin_url = row.get("linkedin_url")
        company_domain = row.get("company_domain")
        if not isinstance(linkedin_url, str) or not isinstance(company_domain, str):
            continue
        key = (linkedin_url, _normalize_domain(company_domain))
        candidate = best_by_key.get(key)
        if candidate is None:
            best_by_key[key] = row
            continue

        candidate_is_current = bool(candidate.get("is_current"))
        row_is_current = bool(row.get("is_current"))
        if candidate_is_current and not row_is_current:
            best_by_key[key] = row
            continue
        if candidate_is_current == row_is_current:
            candidate_end = _to_date(candidate.get("end_date")) or date.min
            row_end = _to_date(row.get("end_date")) or date.min
            if row_end > candidate_end:
                best_by_key[key] = row
                continue
            if row_end == candidate_end:
                candidate_start = _to_date(candidate.get("start_date")) or date.min
                row_start = _to_date(row.get("start_date")) or date.min
                if row_start > candidate_start:
                    best_by_key[key] = row
    return best_by_key


def get_alumni_gtm_leads(
    *,
    origin_company_domain: str,
    gtm_fit: bool | None = None,
    prior_company_domain: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AlumniGtmLeadsResponse:
    normalized_origin_domain = _normalize_domain(origin_company_domain)
    normalized_prior_domain = _normalize_domain(prior_company_domain) if prior_company_domain else None
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    cache_key = _cache_key(
        origin_company_domain=normalized_origin_domain,
        gtm_fit=gtm_fit,
        prior_company_domain=normalized_prior_domain,
        limit=safe_limit,
        offset=safe_offset,
    )
    cached = _get_cached_response(cache_key)
    if cached is not None:
        return cached

    company_target_query = (
        _table("core", "company_targets")
        .select(
            "target_company_name,target_company_domain,target_company_linkedin_url,gtm_fit,reason"
        )
        .eq("origin_company_domain", normalized_origin_domain)
    )
    if gtm_fit is not None:
        company_target_query = company_target_query.eq("gtm_fit", gtm_fit)
    if normalized_prior_domain:
        company_target_query = company_target_query.eq("target_company_domain", normalized_prior_domain)

    company_targets = company_target_query.execute().data or []
    if not company_targets:
        empty = AlumniGtmLeadsResponse(
            origin_company_domain=normalized_origin_domain,
            total_leads=0,
            total_prior_companies=0,
            leads=[],
            prior_companies_summary=[],
        )
        _set_cached_response(cache_key, empty)
        return empty

    company_target_by_domain: dict[str, dict[str, Any]] = {}
    for row in company_targets:
        domain = _normalize_domain(row.get("target_company_domain") or "")
        if not domain:
            continue
        company_target_by_domain[domain] = row
    target_domains = list(company_target_by_domain.keys())
    if not target_domains:
        empty = AlumniGtmLeadsResponse(
            origin_company_domain=normalized_origin_domain,
            total_leads=0,
            total_prior_companies=0,
            leads=[],
            prior_companies_summary=[],
        )
        _set_cached_response(cache_key, empty)
        return empty

    total_count_result = (
        _table("core", "people_targets")
        .select("id", count="exact", head=True)
        .in_("domain", target_domains)
        .execute()
    )
    total_leads = int(total_count_result.count or 0)

    people_target_rows = (
        _table("core", "people_targets")
        .select(
            "id,full_name,first_name,last_name,person_linkedin_url,cleaned_job_title,company_name,domain,company_linkedin_url"
        )
        .in_("domain", target_domains)
        .order("full_name")
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
        .data
        or []
    )

    linkedin_urls = sorted(
        {
            (row.get("person_linkedin_url") or "").strip()
            for row in people_target_rows
            if isinstance(row.get("person_linkedin_url"), str) and row.get("person_linkedin_url").strip()
        }
    )
    current_domains = sorted(
        {
            _normalize_domain(row.get("domain") or "")
            for row in people_target_rows
            if isinstance(row.get("domain"), str) and _normalize_domain(row.get("domain") or "")
        }
    )

    work_history_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    person_profile_by_linkedin: dict[str, dict[str, Any]] = {}
    firmographics_by_domain: dict[str, dict[str, Any]] = {}
    storeleads_by_domain: dict[str, dict[str, Any]] = {}
    core_company_by_domain: dict[str, dict[str, Any]] = {}
    tech_by_domain: dict[str, list[str]] = {}
    meta_ads_by_domain: dict[str, list[dict[str, Any]]] = {}
    google_ads_by_domain: dict[str, list[dict[str, Any]]] = {}

    if linkedin_urls and current_domains:
        work_history_rows = (
            _table("core", "person_work_history")
            .select("linkedin_url,company_domain,title,start_date,end_date,is_current")
            .in_("linkedin_url", linkedin_urls)
            .in_("company_domain", current_domains)
            .execute()
            .data
            or []
        )
        work_history_by_key = _resolve_best_work_history(work_history_rows)

    if linkedin_urls:
        person_profiles = (
            _table("extracted", "person_profile")
            .select("linkedin_url,headline,location_name")
            .in_("linkedin_url", linkedin_urls)
            .execute()
            .data
            or []
        )
        person_profile_by_linkedin = {
            row["linkedin_url"]: row
            for row in person_profiles
            if isinstance(row.get("linkedin_url"), str)
        }

    if current_domains:
        firmographics = (
            _table("extracted", "company_firmographics")
            .select(
                "company_domain,name,linkedin_url,industry,employee_count,size_range,founded_year,country,city,state,description"
            )
            .in_("company_domain", current_domains)
            .execute()
            .data
            or []
        )
        firmographics_by_domain = {
            _normalize_domain(row.get("company_domain") or ""): row
            for row in firmographics
            if isinstance(row.get("company_domain"), str)
        }

        storeleads_rows = (
            _table("extracted", "storeleads_company")
            .select("domain,platform,estimated_sales_yearly,product_count,rank")
            .in_("domain", current_domains)
            .execute()
            .data
            or []
        )
        storeleads_by_domain = {
            _normalize_domain(row.get("domain") or ""): row
            for row in storeleads_rows
            if isinstance(row.get("domain"), str)
        }

        core_company_rows = (
            _table("core", "companies")
            .select("domain,name,linkedin_url")
            .in_("domain", current_domains)
            .execute()
            .data
            or []
        )
        core_company_by_domain = {
            _normalize_domain(row.get("domain") or ""): row
            for row in core_company_rows
            if isinstance(row.get("domain"), str)
        }

        meta_ads_rows = (
            _table("extracted", "company_meta_ads")
            .select(
                "domain,ad_id,platform,start_date,status,page_name,ad_creative_body,landing_page_url,image_url,created_at"
            )
            .in_("domain", current_domains)
            .order("created_at", desc=True)
            .execute()
            .data
            or []
        )
        for row in meta_ads_rows:
            domain = _normalize_domain(row.get("domain") or "")
            if not domain:
                continue
            meta_ads_by_domain.setdefault(domain, []).append(row)

        google_ads_rows = (
            _table("extracted", "company_google_ads")
            .select(
                "domain,creative_id,format,start_date,last_seen,advertiser_name,original_url,variant_content,created_at"
            )
            .in_("domain", current_domains)
            .order("last_seen", desc=True)
            .execute()
            .data
            or []
        )
        for row in google_ads_rows:
            domain = _normalize_domain(row.get("domain") or "")
            if not domain:
                continue
            google_ads_by_domain.setdefault(domain, []).append(row)

        tech_rows = (
            _table("extracted", "storeleads_technology")
            .select("domain,name")
            .in_("domain", current_domains)
            .execute()
            .data
            or []
        )
        for row in tech_rows:
            domain = _normalize_domain(row.get("domain") or "")
            technology = row.get("name")
            if domain and isinstance(technology, str) and technology.strip():
                tech_by_domain.setdefault(domain, []).append(technology.strip())

    summary_items: list[AlumniGtmPriorCompanySummary] = []
    for domain, target in company_target_by_domain.items():
        domain_count_result = (
            _table("core", "people_targets")
            .select("id", count="exact", head=True)
            .eq("domain", domain)
            .execute()
        )
        lead_count = int(domain_count_result.count or 0)
        if lead_count <= 0:
            continue
        summary_items.append(
            AlumniGtmPriorCompanySummary(
                name=target.get("target_company_name"),
                domain=domain,
                lead_count=lead_count,
            )
        )
    summary_items.sort(key=lambda item: (-item.lead_count, item.domain))

    leads: list[AlumniGtmLead] = []
    for row in people_target_rows:
        linkedin_url = (row.get("person_linkedin_url") or "").strip()
        current_domain = _normalize_domain(row.get("domain") or "")
        company_target = company_target_by_domain.get(current_domain, {})
        if not company_target:
            continue

        person_profile = person_profile_by_linkedin.get(linkedin_url, {})
        work_history = work_history_by_key.get((linkedin_url, current_domain), {})
        firmographics = firmographics_by_domain.get(current_domain, {})
        storeleads = storeleads_by_domain.get(current_domain, {})
        core_company = core_company_by_domain.get(current_domain, {})
        technologies = sorted(set(tech_by_domain.get(current_domain, [])))
        meta_ads = meta_ads_by_domain.get(current_domain, [])
        google_ads = google_ads_by_domain.get(current_domain, [])

        lead = AlumniGtmLead(
            person=AlumniGtmPerson(
                full_name=row.get("full_name"),
                first_name=row.get("first_name"),
                last_name=row.get("last_name"),
                linkedin_url=linkedin_url or None,
                headline=person_profile.get("headline"),
                location=person_profile.get("location_name"),
            ),
            current_company=AlumniGtmCurrentCompany(
                name=row.get("company_name") or firmographics.get("name") or core_company.get("name"),
                domain=current_domain or None,
                linkedin_url=row.get("company_linkedin_url")
                or firmographics.get("linkedin_url")
                or core_company.get("linkedin_url"),
                role=row.get("cleaned_job_title"),
                cleaned_job_title=row.get("cleaned_job_title"),
                firmographics=AlumniGtmFirmographics(
                    industry=firmographics.get("industry"),
                    employee_count=firmographics.get("employee_count"),
                    size_range=firmographics.get("size_range"),
                    founded_year=firmographics.get("founded_year"),
                    country=firmographics.get("country"),
                    city=firmographics.get("city"),
                    state=firmographics.get("state"),
                    description=firmographics.get("description"),
                ),
                storeleads=AlumniGtmStoreleads(
                    platform=storeleads.get("platform"),
                    estimated_sales_yearly=storeleads.get("estimated_sales_yearly"),
                    product_count=storeleads.get("product_count"),
                    rank=storeleads.get("rank"),
                    technologies=technologies,
                ),
                ads=AlumniGtmAds(
                    meta_ads_count=len(meta_ads),
                    google_ads_count=len(google_ads),
                    latest_meta_ad=meta_ads[0] if meta_ads else None,
                    latest_google_ad=google_ads[0] if google_ads else None,
                ),
            ),
            prior_company=AlumniGtmPriorCompany(
                name=company_target.get("target_company_name"),
                domain=company_target.get("target_company_domain"),
                linkedin_url=company_target.get("target_company_linkedin_url"),
                role=work_history.get("title"),
                start_date=_to_date(work_history.get("start_date")),
                end_date=_to_date(work_history.get("end_date")),
                gtm_fit=company_target.get("gtm_fit"),
                gtm_fit_reason=company_target.get("reason"),
            ),
        )
        leads.append(lead)

    response = AlumniGtmLeadsResponse(
        origin_company_domain=normalized_origin_domain,
        total_leads=total_leads,
        total_prior_companies=len(summary_items),
        leads=leads,
        prior_companies_summary=summary_items,
    )
    _set_cached_response(cache_key, response)
    return response
