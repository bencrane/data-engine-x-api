from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.auth.models import AuthContext
from app.routers import coverage_v1


class _Query:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self._filters: list[tuple[str, str, Any]] = []
        self._limit: int | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field: str, value: Any):
        self._filters.append(("eq", field, value))
        return self

    def in_(self, field: str, values: list[Any]):
        self._filters.append(("in", field, values))
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def execute(self):
        filtered = list(self._rows)
        for filter_type, field, value in self._filters:
            if filter_type == "eq":
                filtered = [row for row in filtered if row.get(field) == value]
            elif filter_type == "in":
                allowed = set(value)
                filtered = [row for row in filtered if row.get(field) in allowed]
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return SimpleNamespace(data=filtered)


class _Table:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return _Query(self._rows)


class _SupabaseStub:
    def __init__(self, *, company_rows: list[dict[str, Any]], person_rows: list[dict[str, Any]]):
        self._company_rows = company_rows
        self._person_rows = person_rows

    def table(self, table_name: str):
        if table_name == "company_entities":
            return _Table(self._company_rows)
        if table_name == "person_entities":
            return _Table(self._person_rows)
        raise AssertionError(f"Unexpected table: {table_name}")


def _tenant_auth() -> AuthContext:
    return AuthContext(
        user_id="user-1",
        org_id="11111111-1111-1111-1111-111111111111",
        company_id=None,
        role="org_admin",
        auth_method="jwt",
    )


def _mock_revenueinfra(
    monkeypatch: pytest.MonkeyPatch,
    *,
    customers: list[str],
    competitors: list[str],
    similar_companies: list[str],
    alumni_domains: list[str],
    champion_domains: list[str],
) -> None:
    async def _lookup_customers(**_kwargs):
        return {
            "mapped": {
                "customers": [{"customer_domain": domain} for domain in customers],
                "customer_count": len(customers),
            }
        }

    async def _discover_competitors(**_kwargs):
        return {"mapped": {"competitors": [{"domain": domain} for domain in competitors]}}

    async def _find_similar_companies(**_kwargs):
        return {
            "mapped": {
                "similar_companies": [{"company_domain": domain} for domain in similar_companies],
                "similar_count": len(similar_companies),
            }
        }

    async def _lookup_alumni(**_kwargs):
        return {
            "mapped": {
                "alumni": [{"current_company_domain": domain} for domain in alumni_domains],
                "alumni_count": len(alumni_domains),
            }
        }

    async def _lookup_champions(**_kwargs):
        return {
            "mapped": {
                "champions": [{"company_domain": domain} for domain in champion_domains],
                "champion_count": len(champion_domains),
            }
        }

    monkeypatch.setattr(coverage_v1.revenueinfra, "lookup_customers", _lookup_customers)
    monkeypatch.setattr(coverage_v1.revenueinfra, "discover_competitors", _discover_competitors)
    monkeypatch.setattr(coverage_v1.revenueinfra, "find_similar_companies", _find_similar_companies)
    monkeypatch.setattr(coverage_v1.revenueinfra, "lookup_alumni", _lookup_alumni)
    monkeypatch.setattr(coverage_v1.revenueinfra, "lookup_champions", _lookup_champions)


@pytest.mark.asyncio
async def test_coverage_check_fully_enriched_target_ready(monkeypatch: pytest.MonkeyPatch):
    company_rows = [
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "withcoverage.com",
            "canonical_name": "WithCoverage",
            "industry": "Insurance",
            "employee_count": 120,
            "canonical_payload": {"g2_url": "https://g2.com/withcoverage", "pricing_page_url": "https://withcoverage.com/pricing"},
            "company_id": "company-1",
        },
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "customer-a.com",
            "canonical_name": "Customer A",
            "industry": "Fintech",
            "employee_count": 80,
            "canonical_payload": {"g2_url": "https://g2.com/customer-a", "pricing_page_url": "https://customer-a.com/pricing"},
            "company_id": "company-1",
        },
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "customer-b.com",
            "canonical_name": "Customer B",
            "industry": "Healthcare",
            "employee_count": 55,
            "canonical_payload": {"g2_url": "https://g2.com/customer-b", "pricing_page_url": "https://customer-b.com/pricing"},
            "company_id": "company-1",
        },
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "competitor-a.com",
            "canonical_name": "Competitor A",
            "industry": "Insurance",
            "employee_count": 200,
            "canonical_payload": {"g2_url": "https://g2.com/competitor-a", "pricing_page_url": "https://competitor-a.com/pricing"},
            "company_id": "company-1",
        },
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "similar-a.com",
            "canonical_name": "Similar A",
            "industry": "Insurance",
            "employee_count": 140,
            "canonical_payload": {"g2_url": "https://g2.com/similar-a", "pricing_page_url": "https://similar-a.com/pricing"},
            "company_id": "company-1",
        },
    ]
    person_rows = [
        {"work_email": "a@customer-a.com", "email_status": "safe", "canonical_payload": {"company_domain": "customer-a.com"}},
        {"work_email": "b@customer-b.com", "email_status": "safe", "canonical_payload": {"company_domain": "customer-b.com"}},
        {"work_email": "c@competitor-a.com", "email_status": "safe", "canonical_payload": {"company_domain": "competitor-a.com"}},
        {"work_email": None, "email_status": "unknown", "canonical_payload": {"company_domain": "similar-a.com"}},
    ]

    monkeypatch.setattr(
        coverage_v1,
        "get_supabase_client",
        lambda: _SupabaseStub(company_rows=company_rows, person_rows=person_rows),
    )
    _mock_revenueinfra(
        monkeypatch,
        customers=["customer-a.com", "customer-b.com"],
        competitors=["competitor-a.com"],
        similar_companies=["similar-a.com"],
        alumni_domains=["customer-a.com"],
        champion_domains=["competitor-a.com"],
    )

    response = await coverage_v1.coverage_check(
        coverage_v1.CoverageCheckRequest(domain="withcoverage.com"),
        _tenant_auth(),
    )
    data = response.data

    assert data["target"]["enriched"] is True
    assert data["target"]["company_name"] == "WithCoverage"
    assert data["overall_readiness"] == "ready"
    assert data["customers"]["known_count"] == 2
    assert data["customers"]["enriched_count"] == 2
    assert data["customers"]["with_industry"] == 2
    assert data["customers"]["with_employees"] == 2
    assert data["people"]["total_count"] == 4
    assert data["people"]["with_verified_email"] == 3
    assert data["people"]["email_coverage_pct"] == 75.0


@pytest.mark.asyncio
async def test_coverage_check_target_not_in_entity_state_returns_none(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        coverage_v1,
        "get_supabase_client",
        lambda: _SupabaseStub(company_rows=[], person_rows=[]),
    )
    _mock_revenueinfra(
        monkeypatch,
        customers=["customer-a.com", "customer-b.com"],
        competitors=["competitor-a.com"],
        similar_companies=["similar-a.com"],
        alumni_domains=["alumni-company.com"],
        champion_domains=["champion-company.com"],
    )

    response = await coverage_v1.coverage_check(
        coverage_v1.CoverageCheckRequest(domain="missing.com"),
        _tenant_auth(),
    )

    assert response.data["target"]["enriched"] is False
    assert response.data["overall_readiness"] == "none"
    assert "Run company profile enrichment first" in response.data["recommendation"]


@pytest.mark.asyncio
async def test_coverage_check_partial_returns_partial_and_enrichment_recommendation(monkeypatch: pytest.MonkeyPatch):
    company_rows = [
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "withcoverage.com",
            "canonical_name": "WithCoverage",
            "industry": "Insurance",
            "employee_count": 120,
            "canonical_payload": {},
            "company_id": "company-1",
        },
        {
            "org_id": "11111111-1111-1111-1111-111111111111",
            "canonical_domain": "customer-a.com",
            "canonical_name": "Customer A",
            "industry": "Fintech",
            "employee_count": 80,
            "canonical_payload": {},
            "company_id": "company-1",
        },
    ]
    person_rows = [
        {"work_email": None, "email_status": "unknown", "canonical_payload": {"company_domain": "customer-a.com"}},
    ]

    monkeypatch.setattr(
        coverage_v1,
        "get_supabase_client",
        lambda: _SupabaseStub(company_rows=company_rows, person_rows=person_rows),
    )
    _mock_revenueinfra(
        monkeypatch,
        customers=["customer-a.com", "customer-b.com", "customer-c.com"],
        competitors=["competitor-a.com"],
        similar_companies=["similar-a.com", "similar-b.com"],
        alumni_domains=["alumni-company.com"],
        champion_domains=["champion-company.com"],
    )

    response = await coverage_v1.coverage_check(
        coverage_v1.CoverageCheckRequest(domain="withcoverage.com"),
        _tenant_auth(),
    )
    data = response.data

    assert data["overall_readiness"] == "partial"
    assert data["customers"]["known_count"] == 3
    assert data["customers"]["enriched_count"] == 1
    assert "Enrich" in data["recommendation"]
    assert "person search" in data["recommendation"]


@pytest.mark.asyncio
async def test_coverage_check_missing_domain_returns_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        coverage_v1,
        "get_supabase_client",
        lambda: _SupabaseStub(company_rows=[], person_rows=[]),
    )
    _mock_revenueinfra(
        monkeypatch,
        customers=[],
        competitors=[],
        similar_companies=[],
        alumni_domains=[],
        champion_domains=[],
    )

    response = await coverage_v1.coverage_check(
        coverage_v1.CoverageCheckRequest(domain="   "),
        _tenant_auth(),
    )
    assert response.status_code == 400
    assert response.body == b'{"error":"domain is required"}'
