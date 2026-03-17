"""Tests for Federal Leads NAICS metrics — service + endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.federal_leads_naics_metrics import get_naics_metrics, get_naics_agency_breakdown

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────

SAMPLE_NAICS_ROW = {
    "naics_code": "541330",
    "naics_description": "Engineering Services",
    "total_companies": 120,
    "total_awards": 350,
    "total_transactions": 980,
    "total_obligated": 45000000.0,
    "average_award_value": 128571.43,
    "median_award_value": 95000.0,
    "first_time_awardee_companies": 30,
    "repeat_awardee_companies": 90,
    "repeat_awardee_total_obligated": 38000000.0,
    "repeat_awardee_avg_awards": 4.2,
    "total_matched": 847,
}

SAMPLE_AGENCY_ROW = {
    "awarding_agency_code": "097",
    "awarding_agency_name": "Department of Defense",
    "total_companies": 80,
    "total_awards": 200,
    "total_obligated": 30000000.0,
    "first_time_awardee_companies": 15,
}


def _mock_cursor_factory(rows: list[dict]):
    cursor = MagicMock()
    cursor.fetchall.return_value = [dict(r) for r in rows]
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    return cursor


def _mock_pool(rows: list[dict]):
    cursor = _mock_cursor_factory(rows)
    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    pool = MagicMock()
    pool.connection.return_value = conn
    return pool, cursor


def _make_super_admin():
    from uuid import uuid4
    from app.auth.models import SuperAdminContext
    return SuperAdminContext(super_admin_id=uuid4(), email="test@test.com")


def _override_auth():
    from app.routers.entities_v1 import _resolve_flexible_auth
    sa = _make_super_admin()
    app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
    return lambda: app.dependency_overrides.pop(_resolve_flexible_auth, None)


SUPER_ADMIN_HEADERS = {"Authorization": "Bearer test-super-admin-key"}


# ── 1. NAICS Metrics Service Tests ──────────────────────────────────────────


class TestNaicsMetricsDefault:
    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_default_query_returns_paginated_results_with_all_fields(self, mock_get_pool):
        pool, cursor = _mock_pool([SAMPLE_NAICS_ROW])
        mock_get_pool.return_value = pool

        result = get_naics_metrics()

        assert result["limit"] == 100
        assert result["offset"] == 0
        assert result["total_matched"] == 847
        assert len(result["items"]) == 1
        item = result["items"][0]
        expected_fields = {
            "naics_code", "naics_description", "total_companies", "total_awards",
            "total_transactions", "total_obligated", "average_award_value",
            "median_award_value", "first_time_awardee_companies",
            "repeat_awardee_companies", "repeat_awardee_total_obligated",
            "repeat_awardee_avg_awards",
        }
        assert set(item.keys()) == expected_fields

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_empty_result(self, mock_get_pool):
        pool, _ = _mock_pool([])
        mock_get_pool.return_value = pool

        result = get_naics_metrics()
        assert result["items"] == []
        assert result["total_matched"] == 0


class TestNaicsMetricsFilters:
    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_naics_prefix_generates_like(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics(filters={"naics_prefix": "54"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "naics_code LIKE %s" in sql
        assert "54%" in params

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_state_filter_generates_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics(filters={"state": "VA"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "recipient_state_code = %s" in sql
        assert "VA" in params

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_min_companies_generates_having(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics(filters={"min_companies": 10})

        sql = cursor.execute.call_args[0][0]
        assert "HAVING" in sql
        assert "COUNT(DISTINCT recipient_uei) >= %s" in sql

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_business_size_generates_exact_match(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics(filters={"business_size": "SMALL BUSINESS"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "contracting_officers_determination_of_business_size = %s" in sql
        assert "SMALL BUSINESS" in params

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_multiple_filters_combine(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics(filters={"naics_prefix": "54", "state": "VA", "min_companies": 5})

        sql = cursor.execute.call_args[0][0]
        assert "naics_code LIKE %s" in sql
        assert "recipient_state_code = %s" in sql
        assert "HAVING" in sql
        assert " AND " in sql

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_pagination_limit_offset_total_matched(self, mock_get_pool):
        row = dict(SAMPLE_NAICS_ROW)
        row["total_matched"] = 500
        pool, cursor = _mock_pool([row])
        mock_get_pool.return_value = pool

        result = get_naics_metrics(limit=10, offset=50)

        assert result["limit"] == 10
        assert result["offset"] == 50
        assert result["total_matched"] == 500
        params = cursor.execute.call_args[0][1]
        assert 10 in params
        assert 50 in params

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_null_obligation_returns_zero(self, mock_get_pool):
        row = dict(SAMPLE_NAICS_ROW)
        row["total_obligated"] = None
        row["average_award_value"] = None
        row["median_award_value"] = None
        row["repeat_awardee_total_obligated"] = None
        row["repeat_awardee_avg_awards"] = None
        pool, _ = _mock_pool([row])
        mock_get_pool.return_value = pool

        result = get_naics_metrics()
        item = result["items"][0]

        assert item["total_obligated"] == 0.0
        assert item["average_award_value"] == 0.0
        assert item["median_award_value"] == 0.0
        assert item["repeat_awardee_total_obligated"] == 0.0
        assert item["repeat_awardee_avg_awards"] == 0.0

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_repeat_awardee_avg_awards_uses_cte_dedup(self, mock_get_pool):
        """Verify the SQL uses a CTE with DISTINCT to deduplicate repeat awardees."""
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics()

        sql = cursor.execute.call_args[0][0]
        # Must have the repeat_avg CTE with DISTINCT dedup
        assert "repeat_avg" in sql
        assert "SELECT DISTINCT naics_code, recipient_uei, total_awards_count" in sql
        assert "is_first_time_awardee = FALSE" in sql
        assert "AVG(total_awards_count)" in sql

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_median_uses_percentile_cont(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_metrics()

        sql = cursor.execute.call_args[0][0]
        assert "PERCENTILE_CONT(0.5)" in sql


# ── 2. Agency Breakdown Service Tests ───────────────────────────────────────


class TestNaicsAgencyBreakdown:
    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_returns_list_of_agency_dicts(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_AGENCY_ROW])
        mock_get_pool.return_value = pool

        result = get_naics_agency_breakdown(naics_code="541330")

        assert len(result) == 1
        agency = result[0]
        expected_fields = {
            "awarding_agency_code", "awarding_agency_name", "total_companies",
            "total_awards", "total_obligated", "first_time_awardee_companies",
            "repeat_awardee_companies",
        }
        assert set(agency.keys()) == expected_fields

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_ordered_by_total_obligated_desc(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_naics_agency_breakdown(naics_code="541330")

        sql = cursor.execute.call_args[0][0]
        assert "ORDER BY" in sql
        assert "DESC" in sql

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_first_plus_repeat_equals_total(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_AGENCY_ROW])
        mock_get_pool.return_value = pool

        result = get_naics_agency_breakdown(naics_code="541330")

        for agency in result:
            assert agency["first_time_awardee_companies"] + agency["repeat_awardee_companies"] == agency["total_companies"]

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_empty_naics_returns_empty_list(self, mock_get_pool):
        pool, _ = _mock_pool([])
        mock_get_pool.return_value = pool

        result = get_naics_agency_breakdown(naics_code="999999")
        assert result == []


# ── 3. Endpoint Tests ───────────────────────────────────────────────────────


class TestNaicsMetricsEndpoint:
    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_naics_metrics_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, _ = _mock_pool([SAMPLE_NAICS_ROW])
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/naics-metrics",
                json={"naics_prefix": "54", "limit": 10},
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert "items" in body["data"]
            assert "total_matched" in body["data"]
        finally:
            cleanup()

    def test_naics_metrics_requires_auth(self):
        response = client.post("/api/v1/federal-contract-leads/naics-metrics", json={})
        assert response.status_code == 401


class TestNaicsAgencyEndpoint:
    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_agency_breakdown_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, _ = _mock_pool([SAMPLE_AGENCY_ROW])
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/naics-metrics/541330/agencies",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert body["data"]["naics_code"] == "541330"
            assert "agencies" in body["data"]
        finally:
            cleanup()

    def test_agency_breakdown_requires_auth(self):
        response = client.post("/api/v1/federal-contract-leads/naics-metrics/541330/agencies")
        assert response.status_code == 401

    @patch("app.services.federal_leads_naics_metrics._get_pool")
    def test_invalid_naics_returns_empty_agencies(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, _ = _mock_pool([])
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/naics-metrics/999999/agencies",
                headers=SUPER_ADMIN_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert body["data"]["agencies"] == []
        finally:
            cleanup()
