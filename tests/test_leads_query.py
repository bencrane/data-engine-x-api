from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from app.auth import AuthContext
from app.auth.models import SuperAdminContext
from app.routers import entities_v1
from app.services import leads_query


SAMPLE_LEAD_ROW = {
    "person_entity_id": "aaaa1111-1111-1111-1111-111111111111",
    "full_name": "Jane Doe",
    "first_name": "Jane",
    "last_name": "Doe",
    "linkedin_url": "https://linkedin.com/in/janedoe",
    "title": "VP Sales",
    "seniority": "vp",
    "department": "sales",
    "work_email": "jane@acme.com",
    "email_status": "verified",
    "phone_e164": "+15551234567",
    "contact_confidence": 0.95,
    "person_last_enriched_at": "2026-03-10T00:00:00+00:00",
    "company_entity_id": "bbbb2222-2222-2222-2222-222222222222",
    "company_domain": "acme.com",
    "company_name": "Acme Corp",
    "company_linkedin_url": "https://linkedin.com/company/acme",
    "company_industry": "Technology",
    "company_employee_count": 500,
    "company_employee_range": "201-500",
    "company_revenue_band": "$50M-$100M",
    "company_hq_country": "US",
    "relationship_id": "cccc3333-3333-3333-3333-333333333333",
    "relationship_valid_as_of": "2026-03-10T00:00:00+00:00",
    "total_matched": 1,
}

SAMPLE_UNRESOLVED_ROW = {
    **SAMPLE_LEAD_ROW,
    "company_entity_id": None,
    "company_domain": None,
    "company_name": None,
    "company_linkedin_url": None,
    "company_industry": None,
    "company_employee_count": None,
    "company_employee_range": None,
    "company_revenue_band": None,
    "company_hq_country": None,
}

ORG_ID = "11111111-1111-1111-1111-111111111111"


def _make_tenant_auth() -> AuthContext:
    return AuthContext(
        org_id=ORG_ID,
        company_id="22222222-2222-2222-2222-222222222222",
        user_id="33333333-3333-3333-3333-333333333333",
        role="org_admin",
        auth_method="jwt",
    )


def _make_super_admin_auth() -> SuperAdminContext:
    return SuperAdminContext(
        super_admin_id=UUID("00000000-0000-0000-0000-000000000000"),
        email="api-key@super-admin",
    )


def _mock_rpc(monkeypatch: pytest.MonkeyPatch, rows: list[dict]):
    class _RpcResult:
        def execute(self):
            return SimpleNamespace(data=rows)

    class _Client:
        def rpc(self, fn_name, params):
            self.last_fn = fn_name
            self.last_params = params
            return _RpcResult()

    client = _Client()
    monkeypatch.setattr(leads_query, "get_supabase_client", lambda: client)
    return client


@pytest.mark.asyncio
async def test_basic_join_returns_flat_lead_shape(monkeypatch):
    _mock_rpc(monkeypatch, [SAMPLE_LEAD_ROW.copy()])
    auth = _make_tenant_auth()
    payload = entities_v1.LeadsQueryRequest()

    response = await entities_v1.query_leads_endpoint(payload, auth)

    data = response.data
    assert len(data["items"]) == 1
    lead = data["items"][0]
    assert lead["person_entity_id"] == SAMPLE_LEAD_ROW["person_entity_id"]
    assert lead["full_name"] == "Jane Doe"
    assert lead["company_domain"] == "acme.com"
    assert lead["company_industry"] == "Technology"
    assert lead["relationship_id"] == SAMPLE_LEAD_ROW["relationship_id"]
    # total_matched should be stripped from items
    assert "total_matched" not in lead
    assert data["total_matched"] == 1


@pytest.mark.asyncio
async def test_unresolved_company_returns_nulls(monkeypatch):
    _mock_rpc(monkeypatch, [SAMPLE_UNRESOLVED_ROW.copy()])
    auth = _make_tenant_auth()
    payload = entities_v1.LeadsQueryRequest()

    response = await entities_v1.query_leads_endpoint(payload, auth)

    lead = response.data["items"][0]
    assert lead["person_entity_id"] == SAMPLE_LEAD_ROW["person_entity_id"]
    assert lead["full_name"] == "Jane Doe"
    assert lead["company_entity_id"] is None
    assert lead["company_domain"] is None
    assert lead["company_name"] is None
    assert lead["company_industry"] is None


@pytest.mark.asyncio
async def test_filters_are_passed_through(monkeypatch):
    client = _mock_rpc(monkeypatch, [])
    auth = _make_tenant_auth()
    payload = entities_v1.LeadsQueryRequest(
        industry="Technology",
        seniority="vp",
        has_email=True,
        title="Sales",
    )

    await entities_v1.query_leads_endpoint(payload, auth)

    params = client.last_params
    assert params["p_industry"] == "Technology"
    assert params["p_seniority"] == "vp"
    assert params["p_has_email"] is True
    assert params["p_title"] == "Sales"
    assert params["p_org_id"] == ORG_ID


@pytest.mark.asyncio
async def test_auth_scoping_uses_tenant_org_id(monkeypatch):
    client = _mock_rpc(monkeypatch, [])
    auth = _make_tenant_auth()
    # Even if org_id is passed in request, tenant auth overrides it
    payload = entities_v1.LeadsQueryRequest(
        org_id="99999999-9999-9999-9999-999999999999",
    )

    await entities_v1.query_leads_endpoint(payload, auth)

    # Tenant auth should use auth.org_id, not the request body org_id
    assert client.last_params["p_org_id"] == ORG_ID


@pytest.mark.asyncio
async def test_super_admin_org_id_override(monkeypatch):
    override_org = "44444444-4444-4444-4444-444444444444"
    client = _mock_rpc(monkeypatch, [])
    auth = _make_super_admin_auth()
    payload = entities_v1.LeadsQueryRequest(org_id=override_org)

    await entities_v1.query_leads_endpoint(payload, auth)

    assert client.last_params["p_org_id"] == override_org


@pytest.mark.asyncio
async def test_super_admin_without_org_id_returns_error(monkeypatch):
    _mock_rpc(monkeypatch, [])
    auth = _make_super_admin_auth()
    payload = entities_v1.LeadsQueryRequest()

    response = await entities_v1.query_leads_endpoint(payload, auth)

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_pagination(monkeypatch):
    client = _mock_rpc(monkeypatch, [])
    auth = _make_tenant_auth()
    payload = entities_v1.LeadsQueryRequest(limit=50, offset=100)

    await entities_v1.query_leads_endpoint(payload, auth)

    assert client.last_params["p_limit"] == 50
    assert client.last_params["p_offset"] == 100


@pytest.mark.asyncio
async def test_empty_result(monkeypatch):
    _mock_rpc(monkeypatch, [])
    auth = _make_tenant_auth()
    payload = entities_v1.LeadsQueryRequest()

    response = await entities_v1.query_leads_endpoint(payload, auth)

    data = response.data
    assert data["items"] == []
    assert data["total_matched"] == 0
    assert data["limit"] == 25
    assert data["offset"] == 0
