"""Tests for Federal Leads consolidated analytics — temporal first-time definition."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.federal_leads_consolidated_analytics import run_federal_analytics

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────


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


POOL_PATH = "app.services.federal_leads_consolidated_analytics._get_pool"


# ── Sample rows ──────────────────────────────────────────────────────────────

SAMPLE_FIRST_TIME_ROW = {
    "vertical": "Manufacturing",
    "first_time_companies": 1406,
    "first_time_awards": 1823,
    "first_time_total_obligated": 284500000.0,
    "first_time_avg_award_value": 156050.0,
}

SAMPLE_AVG_AWARD_ROW = {
    "vertical": "Construction",
    "first_time_companies": 800,
    "first_time_awards": 950,
    "first_time_avg_award_value": 220000.0,
    "first_time_median_award_value": 180000.0,
    "first_time_total_obligated": 209000000.0,
}

SAMPLE_TOTAL_ROW = {
    "vertical": "IT & Professional Services",
    "total_companies": 3000,
    "total_awards": 5000,
    "total_obligated": 1500000000.0,
    "avg_award_value": 300000.0,
    "first_time_companies": 1200,
    "repeat_companies": 1800,
    "first_time_total_obligated": 500000000.0,
    "repeat_total_obligated": 1000000000.0,
    "first_time_pct": 40.0,
}

SAMPLE_SUB_NAICS_ROW = {
    "naics_code": "541330",
    "naics_description": "Engineering Services",
    "total_companies": 200,
    "first_time_companies": 80,
    "total_awards": 350,
    "total_obligated": 75000000.0,
    "first_time_total_obligated": 25000000.0,
    "avg_award_value": 214285.0,
    "first_time_avg_award_value": 156250.0,
}

SAMPLE_AGENCY_ROW = {
    "awarding_agency_code": "097",
    "awarding_agency_name": "Department of Defense",
    "first_time_companies": 500,
    "first_time_awards": 700,
    "first_time_total_obligated": 150000000.0,
    "first_time_avg_award_value": 214285.0,
    "pct_of_all_first_timers": 35.5,
}

SAMPLE_REPEAT_ROW = {
    "vertical": "Manufacturing",
    "repeat_companies": 2000,
    "avg_cumulative_obligated": 750000.0,
    "median_cumulative_obligated": 500000.0,
    "avg_awards_per_company": 3.5,
    "total_obligated": 1500000000.0,
}


# ── Query Type 1: first_time_awardees_by_naics ──────────────────────────────


class TestFirstTimeAwardeesByNaics:
    def test_returns_all_fields(self):
        pool, _ = _mock_pool([SAMPLE_FIRST_TIME_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_awardees_by_naics",
                params={"date_from": "2025-10-01", "date_to": "2025-12-31"},
            )
        assert result["query_type"] == "first_time_awardees_by_naics"
        item = result["items"][0]
        for field in ("vertical", "first_time_companies", "first_time_awards",
                      "first_time_total_obligated", "first_time_avg_award_value"):
            assert field in item

    def test_dates_required(self):
        with pytest.raises(ValueError, match="date_from and date_to are required"):
            run_federal_analytics(
                query_type="first_time_awardees_by_naics",
                params={},
            )

    def test_limit_caps_results(self):
        rows = [dict(SAMPLE_FIRST_TIME_ROW, vertical=f"V{i}") for i in range(5)]
        pool, cursor = _mock_pool(rows)
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_awardees_by_naics",
                params={"date_from": "2025-10-01", "date_to": "2025-12-31", "limit": 3},
            )
        # Verify LIMIT was passed to SQL
        call_args = cursor.execute.call_args_list
        sql_call = [c for c in call_args if c[0][0].strip().startswith("WITH")]
        assert len(sql_call) == 1
        sql_params = sql_call[0][0][1]
        assert sql_params[-1] == 3  # limit param

    def test_outside_range_excluded(self):
        """Companies whose first action_date is outside the range are excluded via CTE."""
        pool, cursor = _mock_pool([SAMPLE_FIRST_TIME_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_awardees_by_naics",
                params={"date_from": "2025-10-01", "date_to": "2025-12-31"},
            )
        # The CTE filters by first_action_date BETWEEN date_from AND date_to
        sql_call = [c for c in cursor.execute.call_args_list
                    if len(c[0]) > 0 and isinstance(c[0][0], str) and "company_first_dates" in c[0][0]]
        assert len(sql_call) == 1
        sql_params = sql_call[0][0][1]
        # date_from/date_to used twice (CTE + WHERE)
        assert sql_params[0] == "2025-10-01"
        assert sql_params[1] == "2025-12-31"
        assert sql_params[2] == "2025-10-01"
        assert sql_params[3] == "2025-12-31"


# ── Query Type 2: first_time_avg_award_by_naics ─────────────────────────────


class TestFirstTimeAvgAwardByNaics:
    def test_returns_median_field(self):
        pool, _ = _mock_pool([SAMPLE_AVG_AWARD_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_avg_award_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        item = result["items"][0]
        assert "first_time_median_award_value" in item
        assert isinstance(item["first_time_median_award_value"], float)

    def test_ordered_by_avg_desc(self):
        row1 = dict(SAMPLE_AVG_AWARD_ROW, vertical="A", first_time_avg_award_value=500000.0)
        row2 = dict(SAMPLE_AVG_AWARD_ROW, vertical="B", first_time_avg_award_value=100000.0)
        pool, _ = _mock_pool([row1, row2])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_avg_award_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        values = [it["first_time_avg_award_value"] for it in result["items"]]
        assert values == sorted(values, reverse=True)


# ── Query Type 3: total_by_naics ────────────────────────────────────────────


class TestTotalByNaics:
    def test_first_plus_repeat_equals_total(self):
        pool, _ = _mock_pool([SAMPLE_TOTAL_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="total_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        item = result["items"][0]
        assert item["first_time_companies"] + item["repeat_companies"] == item["total_companies"]

    def test_obligated_sums(self):
        pool, _ = _mock_pool([SAMPLE_TOTAL_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="total_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        item = result["items"][0]
        assert abs(
            (item["first_time_total_obligated"] + item["repeat_total_obligated"])
            - item["total_obligated"]
        ) < 0.01

    def test_first_time_pct_range(self):
        pool, _ = _mock_pool([SAMPLE_TOTAL_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="total_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        item = result["items"][0]
        assert 0 <= item["first_time_pct"] <= 100


# ── Query Type 4: sub_naics_breakdown ────────────────────────────────────────


class TestSubNaicsBreakdown:
    def test_naics_prefix_required(self):
        with pytest.raises(ValueError, match="naics_prefix is required"):
            run_federal_analytics(
                query_type="sub_naics_breakdown",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )

    def test_naics_codes_match_prefix(self):
        pool, _ = _mock_pool([SAMPLE_SUB_NAICS_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="sub_naics_breakdown",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31", "naics_prefix": "541"},
            )
        for item in result["items"]:
            assert item["naics_code"].startswith("541")

    def test_returns_naics_description(self):
        pool, _ = _mock_pool([SAMPLE_SUB_NAICS_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="sub_naics_breakdown",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31", "naics_prefix": "541"},
            )
        assert result["items"][0]["naics_description"] == "Engineering Services"


# ── Query Type 5: first_time_by_agency ───────────────────────────────────────


class TestFirstTimeByAgency:
    def test_pct_sums_approx_100(self):
        row1 = dict(SAMPLE_AGENCY_ROW, awarding_agency_code="097", pct_of_all_first_timers=60.0)
        row2 = dict(SAMPLE_AGENCY_ROW, awarding_agency_code="036", pct_of_all_first_timers=40.0)
        pool, _ = _mock_pool([row1, row2])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_by_agency",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        total_pct = sum(it["pct_of_all_first_timers"] for it in result["items"])
        assert abs(total_pct - 100.0) < 1.0

    def test_ordered_by_companies_desc(self):
        row1 = dict(SAMPLE_AGENCY_ROW, first_time_companies=500)
        row2 = dict(SAMPLE_AGENCY_ROW, awarding_agency_code="036", first_time_companies=200)
        pool, _ = _mock_pool([row1, row2])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="first_time_by_agency",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        values = [it["first_time_companies"] for it in result["items"]]
        assert values == sorted(values, reverse=True)


# ── Query Type 6: repeat_awardee_avg_by_naics ───────────────────────────────


class TestRepeatAwardeeAvgByNaics:
    def test_positive_floats(self):
        pool, _ = _mock_pool([SAMPLE_REPEAT_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="repeat_awardee_avg_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        item = result["items"][0]
        assert isinstance(item["avg_cumulative_obligated"], float)
        assert isinstance(item["median_cumulative_obligated"], float)
        assert item["avg_cumulative_obligated"] > 0
        assert item["median_cumulative_obligated"] > 0

    def test_repeat_companies_consistent(self):
        pool, _ = _mock_pool([SAMPLE_REPEAT_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_federal_analytics(
                query_type="repeat_awardee_avg_by_naics",
                params={"date_from": "2025-01-01", "date_to": "2025-12-31"},
            )
        item = result["items"][0]
        assert item["repeat_companies"] > 0
        assert item["total_obligated"] > 0


# ── Unknown query type ──────────────────────────────────────────────────────


def test_unknown_query_type():
    with pytest.raises(ValueError, match="Unknown query_type"):
        run_federal_analytics(query_type="nonexistent")


# ── Endpoint tests ──────────────────────────────────────────────────────────


class TestFederalAnalyticsEndpoint:
    def test_returns_data_envelope(self):
        cleanup = _override_auth()
        try:
            pool, _ = _mock_pool([SAMPLE_FIRST_TIME_ROW])
            with patch(POOL_PATH, return_value=pool):
                resp = client.post(
                    "/api/v1/federal-contract-leads/analytics",
                    json={
                        "query_type": "first_time_awardees_by_naics",
                        "date_from": "2025-10-01",
                        "date_to": "2025-12-31",
                    },
                )
            assert resp.status_code == 200
            body = resp.json()
            assert "data" in body
            assert body["data"]["query_type"] == "first_time_awardees_by_naics"
        finally:
            cleanup()

    def test_400_for_missing_dates(self):
        cleanup = _override_auth()
        try:
            resp = client.post(
                "/api/v1/federal-contract-leads/analytics",
                json={"query_type": "first_time_awardees_by_naics"},
            )
            assert resp.status_code == 400
        finally:
            cleanup()
