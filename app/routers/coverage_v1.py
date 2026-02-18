from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.config import get_settings
from app.database import get_supabase_client
from app.providers import revenueinfra
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()
_security = HTTPBearer(auto_error=False)


class CoverageCheckRequest(BaseModel):
    domain: str
    org_id: str | None = None


async def _resolve_flexible_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthContext | SuperAdminContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    try:
        return await get_current_super_admin(credentials)
    except HTTPException:
        pass
    return await get_current_auth(request=request, credentials=credentials)


def _normalize_domain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned.startswith("http://"):
        cleaned = cleaned[len("http://") :]
    if cleaned.startswith("https://"):
        cleaned = cleaned[len("https://") :]
    cleaned = cleaned.split("/")[0].strip()
    if cleaned.startswith("www."):
        cleaned = cleaned[len("www.") :]
    return cleaned or None


def _query_with_company_scope(query: Any, company_id: str | None) -> Any:
    if company_id:
        return query.eq("company_id", company_id)
    return query


def _extract_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("canonical_payload")
    return payload if isinstance(payload, dict) else {}


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


def _as_domain_list(items: list[dict[str, Any]], field_name: str) -> list[str]:
    domains: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        domain = _normalize_domain(item.get(field_name))
        if domain:
            domains.append(domain)
    return domains


def _coverage_pct(enriched_count: int, known_count: int) -> float:
    if known_count <= 0:
        return 0.0
    return round((enriched_count / known_count) * 100, 1)


def _extract_target_profile(target_row: dict[str, Any] | None, normalized_domain: str) -> dict[str, Any]:
    if target_row is None:
        return {
            "domain": normalized_domain,
            "enriched": False,
            "company_name": None,
            "industry": None,
        }
    payload = _extract_payload(target_row)
    return {
        "domain": normalized_domain,
        "enriched": True,
        "company_name": target_row.get("canonical_name") or payload.get("company_name"),
        "industry": target_row.get("industry") or payload.get("industry_primary"),
    }


def _extract_lookup_domains(mapped: dict[str, Any], category: str) -> tuple[int, list[str]]:
    if category == "customers":
        items = mapped.get("customers") if isinstance(mapped.get("customers"), list) else []
        known_count = mapped.get("customer_count") if isinstance(mapped.get("customer_count"), int) else len(items)
        return known_count, _as_domain_list(items, "customer_domain")

    if category == "competitors":
        items = mapped.get("competitors") if isinstance(mapped.get("competitors"), list) else []
        return len(items), _as_domain_list(items, "domain")

    if category == "similar_companies":
        items = mapped.get("similar_companies") if isinstance(mapped.get("similar_companies"), list) else []
        known_count = mapped.get("similar_count") if isinstance(mapped.get("similar_count"), int) else len(items)
        return known_count, _as_domain_list(items, "company_domain")

    if category == "alumni":
        items = mapped.get("alumni") if isinstance(mapped.get("alumni"), list) else []
        known_count = mapped.get("alumni_count") if isinstance(mapped.get("alumni_count"), int) else len(items)
        return known_count, _as_domain_list(items, "current_company_domain")

    if category == "champions":
        items = mapped.get("champions") if isinstance(mapped.get("champions"), list) else []
        known_count = mapped.get("champion_count") if isinstance(mapped.get("champion_count"), int) else len(items)
        return known_count, _as_domain_list(items, "company_domain")

    return 0, []


def _category_metrics(
    *,
    known_count: int,
    domains: list[str],
    company_by_domain: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    enriched_count = 0
    with_industry = 0
    with_employees = 0
    with_g2_url = 0
    with_pricing_page_url = 0

    for domain in domains:
        company = company_by_domain.get(domain)
        if not company:
            continue
        enriched_count += 1
        payload = _extract_payload(company)
        if company.get("industry") or payload.get("industry_primary"):
            with_industry += 1
        if company.get("employee_count") is not None or payload.get("employee_count") is not None:
            with_employees += 1
        if _as_non_empty_str(payload.get("g2_url")):
            with_g2_url += 1
        if _as_non_empty_str(payload.get("pricing_page_url")):
            with_pricing_page_url += 1

    return {
        "known_count": known_count,
        "enriched_count": enriched_count,
        "coverage_pct": _coverage_pct(enriched_count, known_count),
        "with_industry": with_industry,
        "with_employees": with_employees,
        "with_g2_url": with_g2_url,
        "with_pricing_page_url": with_pricing_page_url,
    }


def _person_company_domain(row: dict[str, Any]) -> str | None:
    payload = _extract_payload(row)
    for key in ("company_domain", "current_company_domain", "canonical_domain", "domain"):
        normalized = _normalize_domain(payload.get(key))
        if normalized:
            return normalized
    return None


def _people_metrics(rows: list[dict[str, Any]], enriched_domains: set[str]) -> dict[str, Any]:
    if not enriched_domains:
        return {
            "total_count": 0,
            "with_email": 0,
            "with_verified_email": 0,
            "email_coverage_pct": 0.0,
        }

    associated_rows = [row for row in rows if _person_company_domain(row) in enriched_domains]
    total_count = len(associated_rows)
    with_email = 0
    with_verified_email = 0
    for row in associated_rows:
        if _as_non_empty_str(row.get("work_email")):
            with_email += 1
        if row.get("email_status") == "safe":
            with_verified_email += 1

    return {
        "total_count": total_count,
        "with_email": with_email,
        "with_verified_email": with_verified_email,
        "email_coverage_pct": _coverage_pct(with_verified_email, total_count),
    }


def _overall_readiness(*, target_enriched: bool, customers_coverage_pct: float, email_coverage_pct: float) -> str:
    if not target_enriched:
        return "none"
    if customers_coverage_pct > 50.0 and email_coverage_pct > 50.0:
        return "ready"
    return "partial"


def _build_recommendation(*, readiness: str, metrics_by_category: dict[str, dict[str, Any]], people: dict[str, Any]) -> str:
    if readiness == "none":
        return "Target company is not enriched. Run company profile enrichment first."
    if readiness == "ready":
        return "Coverage is ready for outbound and portal gating."

    actions: list[str] = []
    customer_remaining = metrics_by_category["customers"]["known_count"] - metrics_by_category["customers"]["enriched_count"]
    if customer_remaining > 0:
        actions.append(f"Enrich {customer_remaining} remaining customers")

    competitor_remaining = (
        metrics_by_category["competitors"]["known_count"] - metrics_by_category["competitors"]["enriched_count"]
    )
    if competitor_remaining > 0 and customer_remaining <= 0:
        actions.append(f"enrich {competitor_remaining} remaining competitors")

    similar_remaining = (
        metrics_by_category["similar_companies"]["known_count"]
        - metrics_by_category["similar_companies"]["enriched_count"]
    )
    if similar_remaining > 0 and customer_remaining <= 0 and competitor_remaining <= 0:
        actions.append(f"enrich {similar_remaining} remaining similar companies")

    if people["total_count"] == 0:
        actions.append("run person search on enriched companies")
    elif people["email_coverage_pct"] <= 50.0:
        missing_verified = max(people["total_count"] - people["with_verified_email"], 0)
        actions.append(f"verify email deliverability for {missing_verified} people")

    if not actions:
        return "Expand enrichment coverage across customers and associated contacts."

    if len(actions) == 1:
        return f"{actions[0]} to improve coverage."
    return f"{actions[0]} and {actions[1]} to improve coverage."


async def _safe_lookup(fn, **kwargs: Any) -> dict[str, Any]:
    try:
        result = await fn(**kwargs)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(result, dict):
        return {}
    mapped = result.get("mapped")
    return mapped if isinstance(mapped, dict) else {}


@router.post(
    "/check",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def coverage_check(
    payload: CoverageCheckRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    normalized_domain = _normalize_domain(payload.domain)
    if not normalized_domain:
        return error_response("domain is required", 400)

    is_super_admin = isinstance(auth, SuperAdminContext)
    if is_super_admin:
        if not payload.org_id:
            return error_response("org_id is required for super-admin coverage checks", 400)
        org_id = payload.org_id
        scoped_company_id: str | None = None
    else:
        org_id = auth.org_id
        scoped_company_id = auth.company_id if auth.role in {"company_admin", "member"} else None
        if auth.role in {"company_admin", "member"} and not scoped_company_id:
            return error_response("Company-scoped user missing company_id", 403)

    client = get_supabase_client()
    target_query = (
        client.table("company_entities")
        .select("canonical_domain, canonical_name, linkedin_url, industry, employee_count, canonical_payload, company_id")
        .eq("org_id", org_id)
        .eq("canonical_domain", normalized_domain)
    )
    target_query = _query_with_company_scope(target_query, scoped_company_id)
    target_result = target_query.limit(1).execute()
    target_row = target_result.data[0] if target_result.data else None
    target = _extract_target_profile(target_row, normalized_domain)
    target_company_name = target["company_name"] or normalized_domain

    settings = get_settings()
    customers_mapped, competitors_mapped, similar_mapped, alumni_mapped, champions_mapped = await asyncio.gather(
        _safe_lookup(
            revenueinfra.lookup_customers,
            base_url=settings.revenueinfra_api_url,
            domain=normalized_domain,
        ),
        _safe_lookup(
            revenueinfra.discover_competitors,
            base_url=settings.revenueinfra_api_url,
            domain=normalized_domain,
            company_name=target_company_name,
            company_linkedin_url=(target_row or {}).get("linkedin_url"),
        ),
        _safe_lookup(
            revenueinfra.find_similar_companies,
            base_url=settings.revenueinfra_api_url,
            domain=normalized_domain,
        ),
        _safe_lookup(
            revenueinfra.lookup_alumni,
            base_url=settings.revenueinfra_api_url,
            domain=normalized_domain,
        ),
        _safe_lookup(
            revenueinfra.lookup_champions,
            base_url=settings.revenueinfra_api_url,
            domain=normalized_domain,
        ),
    )

    lookup_mapped = {
        "customers": customers_mapped,
        "competitors": competitors_mapped,
        "similar_companies": similar_mapped,
        "alumni": alumni_mapped,
        "champions": champions_mapped,
    }

    known_and_domains = {
        category: _extract_lookup_domains(mapped, category)
        for category, mapped in lookup_mapped.items()
    }
    all_domains = {
        domain
        for _, domains in known_and_domains.values()
        for domain in domains
    }
    if target_row is not None:
        all_domains.add(normalized_domain)

    company_by_domain: dict[str, dict[str, Any]] = {}
    if all_domains:
        company_query = (
            client.table("company_entities")
            .select("canonical_domain, canonical_name, linkedin_url, industry, employee_count, canonical_payload, company_id")
            .eq("org_id", org_id)
            .in_("canonical_domain", sorted(all_domains))
        )
        company_query = _query_with_company_scope(company_query, scoped_company_id)
        company_rows = company_query.execute().data
        for row in company_rows:
            normalized = _normalize_domain(row.get("canonical_domain"))
            if normalized:
                company_by_domain[normalized] = row

    metrics_by_category = {
        category: _category_metrics(
            known_count=known_count,
            domains=domains,
            company_by_domain=company_by_domain,
        )
        for category, (known_count, domains) in known_and_domains.items()
    }

    enriched_domains = {domain for domain in all_domains if domain in company_by_domain}
    person_query = (
        client.table("person_entities")
        .select("work_email, email_status, canonical_payload, company_id")
        .eq("org_id", org_id)
    )
    person_query = _query_with_company_scope(person_query, scoped_company_id)
    person_rows = person_query.execute().data
    people = _people_metrics(person_rows, enriched_domains)

    readiness = _overall_readiness(
        target_enriched=target["enriched"],
        customers_coverage_pct=metrics_by_category["customers"]["coverage_pct"],
        email_coverage_pct=people["email_coverage_pct"],
    )
    recommendation = _build_recommendation(
        readiness=readiness,
        metrics_by_category=metrics_by_category,
        people=people,
    )

    return DataEnvelope(
        data={
            "target": target,
            "customers": metrics_by_category["customers"],
            "competitors": metrics_by_category["competitors"],
            "similar_companies": metrics_by_category["similar_companies"],
            "alumni": metrics_by_category["alumni"],
            "champions": metrics_by_category["champions"],
            "people": people,
            "overall_readiness": readiness,
            "recommendation": recommendation,
        }
    )
