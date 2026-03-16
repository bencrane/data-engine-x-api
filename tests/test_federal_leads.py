"""Tests for Federal Contract Leads — query service and endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.federal_leads_query import query_federal_contract_leads

client = TestClient(app)


# ── Fixtures ────────────────────────────────────────────────────────────────

SAMPLE_ROW = {
    "contract_transaction_unique_key": "TXN001",
    "contract_award_unique_key": "AWD001",
    "recipient_uei": "ABC123456789",
    "recipient_name": "ACME CORP",
    "recipient_state_code": "VA",
    "naics_code": "541512",
    "action_date": "2025-06-15",
    "federal_action_obligation": "150000.00",
    "awarding_agency_code": "097",
    "awarding_agency_name": "DEPT OF DEFENSE",
    "contracting_officers_determination_of_business_size": "SMALL BUSINESS",
    "is_first_time_awardee": True,
    "has_sam_match": True,
    "total_awards_count": 1,
    "total_matched": 1,
}


def _mock_cursor_factory(rows: list[dict]):
    """Build a mock cursor that returns dict rows via fetchall."""
    cursor = MagicMock()
    cursor.fetchall.return_value = [dict(r) for r in rows]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


def _mock_pool(rows: list[dict]):
    """Return a patched _get_pool that yields the given rows."""
    cursor = _mock_cursor_factory(rows)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    pool = MagicMock()
    pool.connection.return_value = conn
    return pool, cursor


# ── Query Service Tests ─────────────────────────────────────────────────────


class TestQueryServiceDefaultQuery:
    @patch("app.services.federal_leads_query._get_pool")
    def test_default_no_filters(self, mock_get_pool):
        pool, cursor = _mock_pool([SAMPLE_ROW])
        mock_get_pool.return_value = pool

        result = query_federal_contract_leads(filters={}, limit=25, offset=0)

        assert result["limit"] == 25
        assert result["offset"] == 0
        assert result["total_matched"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["recipient_name"] == "ACME CORP"
        # total_matched should be popped from items
        assert "total_matched" not in result["items"][0]

    @patch("app.services.federal_leads_query._get_pool")
    def test_empty_result(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        result = query_federal_contract_leads(filters={}, limit=25, offset=0)

        assert result["items"] == []
        assert result["total_matched"] == 0


class TestQueryServiceFilters:
    @patch("app.services.federal_leads_query._get_pool")
    def test_naics_prefix_generates_like(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={"naics_prefix": "54"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "naics_code LIKE %s" in sql
        assert "54%" in params

    @patch("app.services.federal_leads_query._get_pool")
    def test_state_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={"state": "VA"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "recipient_state_code = %s" in sql
        assert "VA" in params

    @patch("app.services.federal_leads_query._get_pool")
    def test_action_date_range(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(
            filters={"action_date_from": "2025-01-01", "action_date_to": "2025-12-31"}
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "action_date >= %s" in sql
        assert "action_date <= %s" in sql
        assert "2025-01-01" in params
        assert "2025-12-31" in params

    @patch("app.services.federal_leads_query._get_pool")
    def test_min_obligation_casts_numeric(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={"min_obligation": "100000"})

        sql = cursor.execute.call_args[0][0]
        assert "CAST(federal_action_obligation AS NUMERIC) >= %s" in sql

    @patch("app.services.federal_leads_query._get_pool")
    def test_business_size_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={"business_size": "SMALL BUSINESS"})

        sql = cursor.execute.call_args[0][0]
        assert "contracting_officers_determination_of_business_size = %s" in sql

    @patch("app.services.federal_leads_query._get_pool")
    def test_first_time_only_boolean(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={"first_time_only": True})

        sql = cursor.execute.call_args[0][0]
        assert "is_first_time_awardee = TRUE" in sql

    @patch("app.services.federal_leads_query._get_pool")
    def test_recipient_name_ilike(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={"recipient_name": "acme"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "recipient_name ILIKE %s" in sql
        assert "%acme%" in params

    @patch("app.services.federal_leads_query._get_pool")
    def test_multiple_filters_combine_with_and(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(
            filters={"state": "VA", "first_time_only": True, "naics_prefix": "54"}
        )

        sql = cursor.execute.call_args[0][0]
        assert " AND " in sql
        assert "recipient_state_code = %s" in sql
        assert "is_first_time_awardee = TRUE" in sql
        assert "naics_code LIKE %s" in sql

    @patch("app.services.federal_leads_query._get_pool")
    def test_pagination_limit_offset(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(filters={}, limit=10, offset=50)

        params = cursor.execute.call_args[0][1]
        assert 10 in params
        assert 50 in params

    @patch("app.services.federal_leads_query._get_pool")
    def test_all_values_parameterized(self, mock_get_pool):
        """Verify no string interpolation — all filter values appear as params."""
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        query_federal_contract_leads(
            filters={
                "state": "CA",
                "naics_prefix": "33",
                "recipient_name": "test",
                "min_obligation": "50000",
                "awarding_agency_code": "097",
                "recipient_uei": "XYZ999999999",
                "business_size": "SMALL BUSINESS",
            }
        )

        sql = cursor.execute.call_args[0][0]
        # None of the actual filter values should be embedded in the SQL string
        assert "'CA'" not in sql
        assert "'33%'" not in sql
        assert "'test'" not in sql
        assert "'097'" not in sql


# ── Endpoint Tests ──────────────────────────────────────────────────────────

SUPER_ADMIN_HEADERS = {"Authorization": "Bearer test-super-admin-key"}


def _make_super_admin():
    from uuid import uuid4
    from app.auth.models import SuperAdminContext
    return SuperAdminContext(super_admin_id=uuid4(), email="test@test.com")


def _override_auth():
    """Install dependency override for _resolve_flexible_auth, return cleanup fn."""
    from app.routers.entities_v1 import _resolve_flexible_auth
    sa = _make_super_admin()
    app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
    return lambda: app.dependency_overrides.pop(_resolve_flexible_auth, None)


class TestQueryEndpoint:
    @patch("app.services.federal_leads_query._get_pool")
    def test_query_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, cursor = _mock_pool([SAMPLE_ROW])
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/query",
                json={"state": "VA", "limit": 5},
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert "items" in body["data"]
        finally:
            cleanup()

    def test_query_requires_auth(self):
        response = client.post(
            "/api/v1/federal-contract-leads/query",
            json={},
        )
        assert response.status_code == 401

    def test_invalid_limit_returns_422(self):
        cleanup = _override_auth()
        try:
            response = client.post(
                "/api/v1/federal-contract-leads/query",
                json={"limit": 0},
                headers=SUPER_ADMIN_HEADERS,
            )
            assert response.status_code == 422
        finally:
            cleanup()

    def test_invalid_offset_returns_422(self):
        cleanup = _override_auth()
        try:
            response = client.post(
                "/api/v1/federal-contract-leads/query",
                json={"offset": -1},
                headers=SUPER_ADMIN_HEADERS,
            )
            assert response.status_code == 422
        finally:
            cleanup()


class TestStatsEndpoint:
    @patch("app.services.federal_leads_refresh._get_pool")
    def test_stats_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            cursor = MagicMock()
            cursor.fetchone.return_value = (1000, 500, 200)
            cursor.__enter__ = MagicMock(return_value=cursor)
            cursor.__exit__ = MagicMock(return_value=False)
            conn = MagicMock()
            conn.cursor.return_value = cursor
            conn.__enter__ = MagicMock(return_value=conn)
            conn.__exit__ = MagicMock(return_value=False)
            pool = MagicMock()
            pool.connection.return_value = conn
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/stats",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert body["data"]["total_rows"] == 1000
            assert body["data"]["unique_companies"] == 500
            assert body["data"]["first_time_awardees"] == 200
        finally:
            cleanup()

    def test_stats_requires_auth(self):
        response = client.post("/api/v1/federal-contract-leads/stats")
        assert response.status_code == 401
