"""Tests for external ingest — field mapping, service, and endpoint."""
from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from app.services.external_ingest import (
    ingest_entities,
    map_company_payload,
    map_person_payload,
)
from app.services.entity_state import EntityStateVersionError


# ---------------------------------------------------------------------------
# Sample payloads (from Clay)
# ---------------------------------------------------------------------------

CLAY_COMPANY_FULL = {
    "name": "Russell Tobin",
    "size": "201-500 employees",
    "type": "Privately Held",
    "domain": "russelltobin.com",
    "country": "United States",
    "industry": "Staffing and Recruiting",
    "location": "New York, New York",
    "industries": ["Staffing and Recruiting"],
    "description": "A staffing company",
    "linkedin_url": "https://www.linkedin.com/company/russell-tobin-&-associates-llc",
    "annual_revenue": "25M-75M",
    "clay_company_id": 49371725,
    "resolved_domain": {"is_live": True, "resolved_domain": "russelltobin.com"},
    "derived_datapoints": {"industry": ["Staffing"], "description": "..."},
    "linkedin_company_id": 827183,
    "total_funding_amount_range_usd": "Funding unknown",
}

CLAY_PERSON_FULL = {
    "url": "https://www.linkedin.com/in/lauriecanepa/",
    "name": "Laurie Canepa",
    "domain": "stevendouglas.com",
    "last_name": "Canepa",
    "first_name": "Laurie",
    "location_name": "Austin, Texas, United States",
    "company_table_id": "t_0tbworv5nq5XoEu2xwe",
    "company_record_id": "r_0tbwory2twswCf8544H",
    "latest_experience_title": "Managing Director",
    "latest_experience_company": "StevenDouglas",
    "latest_experience_start_date": "2023-01-01",
}


# ---------------------------------------------------------------------------
# 1-3: Company mapping tests
# ---------------------------------------------------------------------------

class TestMapCompanyPayload:
    def test_all_fields_present(self):
        result = map_company_payload(CLAY_COMPANY_FULL, "clay")

        assert result["canonical_domain"] == "russelltobin.com"
        assert result["canonical_name"] == "Russell Tobin"
        assert result["linkedin_url"] == "https://www.linkedin.com/company/russell-tobin-&-associates-llc"
        assert result["company_linkedin_id"] == "827183"  # cast to string
        assert result["industry"] == "Staffing and Recruiting"
        assert result["employee_range"] == "201-500 employees"
        assert result["hq_country"] == "United States"
        assert result["description"] == "A staffing company"
        assert result["revenue_band"] == "25M-75M"
        assert result["source_providers"] == ["clay"]

    def test_preserves_unmapped_fields(self):
        result = map_company_payload(CLAY_COMPANY_FULL, "clay")

        assert result["clay_company_id"] == 49371725
        assert result["derived_datapoints"] == {"industry": ["Staffing"], "description": "..."}
        assert result["resolved_domain"] == {"is_live": True, "resolved_domain": "russelltobin.com"}
        assert result["type"] == "Privately Held"
        assert result["location"] == "New York, New York"
        assert result["industries"] == ["Staffing and Recruiting"]
        assert result["total_funding_amount_range_usd"] == "Funding unknown"

    def test_minimal_payload(self):
        result = map_company_payload({"domain": "example.com"}, "clay")

        assert result["canonical_domain"] == "example.com"
        assert result["source_providers"] == ["clay"]
        assert "canonical_name" not in result
        assert "linkedin_url" not in result


# ---------------------------------------------------------------------------
# 4-7: Person mapping tests
# ---------------------------------------------------------------------------

class TestMapPersonPayload:
    def test_all_fields_present(self):
        result = map_person_payload(CLAY_PERSON_FULL, "clay")

        assert result["linkedin_url"] == "https://www.linkedin.com/in/lauriecanepa/"
        assert result["full_name"] == "Laurie Canepa"
        assert result["first_name"] == "Laurie"
        assert result["last_name"] == "Canepa"
        assert result["title"] == "Managing Director"
        assert result["current_company_domain"] == "stevendouglas.com"
        assert result["current_company_name"] == "StevenDouglas"
        assert result["source_providers"] == ["clay"]

    def test_preserves_unmapped_fields(self):
        result = map_person_payload(CLAY_PERSON_FULL, "clay")

        assert result["company_table_id"] == "t_0tbworv5nq5XoEu2xwe"
        assert result["company_record_id"] == "r_0tbwory2twswCf8544H"
        assert result["location_name"] == "Austin, Texas, United States"
        assert result["latest_experience_start_date"] == "2023-01-01"

    def test_url_maps_to_linkedin_url(self):
        result = map_person_payload({"url": "https://linkedin.com/in/test"}, "clay")
        assert result["linkedin_url"] == "https://linkedin.com/in/test"
        assert "url" not in result

    def test_domain_maps_to_current_company_domain(self):
        result = map_person_payload({"domain": "example.com"}, "clay")
        assert result["current_company_domain"] == "example.com"
        assert "canonical_domain" not in result
        assert "domain" not in result


# ---------------------------------------------------------------------------
# 8-11: Service tests (mock DB calls)
# ---------------------------------------------------------------------------

class TestIngestEntities:
    @patch("app.services.external_ingest.upsert_company_entity")
    def test_company_ingest_creates_entity(self, mock_upsert):
        mock_upsert.return_value = {"entity_id": "e1", "record_version": 1}

        summary = ingest_entities(
            org_id="org1",
            company_id=None,
            entity_type="company",
            source_provider="clay",
            payloads=[{"domain": "example.com", "name": "Example"}],
        )

        assert summary["created"] == 1
        assert summary["updated"] == 0
        assert summary["total_submitted"] == 1
        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args.kwargs
        assert call_kwargs["org_id"] == "org1"
        assert call_kwargs["last_operation_id"] == "external.ingest.clay"
        assert call_kwargs["last_run_id"] is None

    @patch("app.services.external_ingest._resolve_company_by_domain")
    @patch("app.services.external_ingest.record_entity_relationship")
    @patch("app.services.external_ingest.upsert_person_entity")
    def test_person_ingest_creates_entity_and_works_at_edge(
        self, mock_upsert, mock_record_rel, mock_resolve
    ):
        mock_upsert.return_value = {"entity_id": "p1", "record_version": 1}
        mock_resolve.return_value = "c1"
        mock_record_rel.return_value = {"id": "rel1"}

        summary = ingest_entities(
            org_id="org1",
            company_id=None,
            entity_type="person",
            source_provider="clay",
            payloads=[CLAY_PERSON_FULL],
        )

        assert summary["created"] == 1
        assert summary["relationships_created"] == 1
        assert summary["relationships_matched"] == 1
        assert summary["relationships_unmatched"] == 0

        mock_record_rel.assert_called_once()
        rel_kwargs = mock_record_rel.call_args.kwargs
        assert rel_kwargs["relationship"] == "works_at"
        assert rel_kwargs["source_entity_id"] == "p1"
        assert rel_kwargs["target_entity_id"] == "c1"
        assert rel_kwargs["metadata"]["source"] == "external_ingest"
        assert rel_kwargs["metadata"]["source_provider"] == "clay"

    @patch("app.services.external_ingest.upsert_company_entity")
    def test_batch_error_handling(self, mock_upsert):
        mock_upsert.side_effect = [
            {"entity_id": "e1", "record_version": 1},
            RuntimeError("DB connection failed"),
            {"entity_id": "e3", "record_version": 1},
        ]

        summary = ingest_entities(
            org_id="org1",
            company_id=None,
            entity_type="company",
            source_provider="clay",
            payloads=[
                {"domain": "a.com"},
                {"domain": "b.com"},
                {"domain": "c.com"},
            ],
        )

        assert summary["created"] == 2
        assert summary["errors"] == 1
        assert len(summary["error_details"]) == 1
        assert summary["error_details"][0]["index"] == 1
        assert "DB connection failed" in summary["error_details"][0]["error"]

    @patch("app.services.external_ingest.upsert_company_entity")
    def test_version_conflict_counted_as_skipped(self, mock_upsert):
        mock_upsert.side_effect = EntityStateVersionError("version conflict")

        summary = ingest_entities(
            org_id="org1",
            company_id=None,
            entity_type="company",
            source_provider="clay",
            payloads=[{"domain": "example.com"}],
        )

        assert summary["skipped"] == 1
        assert summary["created"] == 0
        assert summary["errors"] == 0


# ---------------------------------------------------------------------------
# 12-14: Endpoint tests (mock service)
# ---------------------------------------------------------------------------

class TestBulkEntityIngestEndpoint:
    @patch("app.routers.entities_v1.ingest_entities")
    def test_tenant_auth_uses_auth_org_id(self, mock_ingest):
        mock_ingest.return_value = {
            "entity_type": "company",
            "source_provider": "clay",
            "total_submitted": 1,
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        }

        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth import AuthContext
        from app.routers.entities_v1 import _resolve_flexible_auth

        tenant_auth = AuthContext(
            org_id="tenant-org-1",
            company_id="tenant-co-1",
            user_id="u1",
            role="org_admin",
            auth_method="api_token",
        )
        app.dependency_overrides[_resolve_flexible_auth] = lambda: tenant_auth
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/entities/ingest",
                json={
                    "entity_type": "company",
                    "source_provider": "clay",
                    "payloads": [{"domain": "example.com"}],
                },
            )
            assert response.status_code == 200
            call_kwargs = mock_ingest.call_args.kwargs
            assert call_kwargs["org_id"] == "tenant-org-1"
            assert call_kwargs["company_id"] == "tenant-co-1"
        finally:
            app.dependency_overrides.pop(_resolve_flexible_auth, None)

    @patch("app.routers.entities_v1.ingest_entities")
    def test_super_admin_org_id_override(self, mock_ingest):
        mock_ingest.return_value = {
            "entity_type": "company",
            "source_provider": "clay",
            "total_submitted": 1,
            "created": 1,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "error_details": [],
        }

        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth.models import SuperAdminContext
        from app.routers.entities_v1 import _resolve_flexible_auth

        sa = SuperAdminContext(super_admin_id=uuid4(), email="admin@test.com")
        app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/entities/ingest",
                json={
                    "entity_type": "company",
                    "source_provider": "clay",
                    "payloads": [{"domain": "example.com"}],
                    "org_id": "override-org",
                    "company_id": "override-co",
                },
            )
            assert response.status_code == 200
            call_kwargs = mock_ingest.call_args.kwargs
            assert call_kwargs["org_id"] == "override-org"
            assert call_kwargs["company_id"] == "override-co"
        finally:
            app.dependency_overrides.pop(_resolve_flexible_auth, None)

    def test_super_admin_without_org_id_returns_400(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth.models import SuperAdminContext
        from app.routers.entities_v1 import _resolve_flexible_auth

        sa = SuperAdminContext(super_admin_id=uuid4(), email="admin@test.com")
        app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/entities/ingest",
                json={
                    "entity_type": "company",
                    "source_provider": "clay",
                    "payloads": [{"domain": "example.com"}],
                },
            )
            assert response.status_code == 400
            assert "org_id" in response.json()["error"]
        finally:
            app.dependency_overrides.pop(_resolve_flexible_auth, None)
