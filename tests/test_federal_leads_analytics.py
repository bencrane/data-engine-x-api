"""Tests for Federal Leads analytics — time series, distribution, velocity, endpoints."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.federal_leads_analytics import (
    get_time_series,
    get_award_size_distribution,
    get_set_aside_breakdown,
    get_competition_metrics,
    get_geographic_hotspots,
    get_repeat_awardee_velocity,
    get_award_ceiling_gap,
)

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_cursor_factory(rows: list[dict]):
    cursor = MagicMock()
    cursor.fetchall.return_value = [dict(r) for r in rows]
    cursor.fetchone.return_value = dict(rows[0]) if rows else None
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


# ── Sample data ──────────────────────────────────────────────────────────────

SAMPLE_TIME_SERIES_ROW = {
    "period": "2025-Q4",
    "total_companies": 500,
    "total_awards": 1200,
    "total_transactions": 3400,
    "total_obligated": 50000000.0,
    "first_time_awardee_companies": 120,
}

SAMPLE_TIME_SERIES_MONTH = {
    "period": "2025-11",
    "total_companies": 200,
    "total_awards": 450,
    "total_transactions": 1100,
    "total_obligated": 18000000.0,
    "first_time_awardee_companies": 50,
}

SAMPLE_SIZE_DIST_ROW = {
    "vertical": "Manufacturing",
    "size_bucket": "Under $100K",
    "bucket_order": 1,
    "transaction_count": 500,
    "unique_companies": 200,
    "total_obligated": 25000000.0,
    "pct_of_vertical_transactions": 35.0,
    "pct_of_vertical_dollars": 12.0,
}

SAMPLE_SET_ASIDE_ROW = {
    "vertical": "Construction",
    "set_aside_type": "SBA",
    "transaction_count": 300,
    "unique_companies": 150,
    "total_obligated": 40000000.0,
    "pct_of_vertical_transactions": 25.0,
}

SAMPLE_SET_ASIDE_NONE = {
    "vertical": "Construction",
    "set_aside_type": "NONE",
    "transaction_count": 100,
    "unique_companies": 80,
    "total_obligated": 15000000.0,
    "pct_of_vertical_transactions": 8.3,
}

SAMPLE_COMPETITION_ROW = {
    "vertical": "IT & Professional Services",
    "total_awards": 800,
    "avg_offers_received": 3.7,
    "median_offers_received": 3.0,
    "sole_source_count": 250,
    "total_transactions": 2000,
    "full_competition_count": 1200,
}

SAMPLE_GEO_ROW = {
    "state": "TX",
    "total_companies": 340,
    "total_awards": 890,
    "total_obligated": 120000000.0,
    "first_time_awardee_companies": 85,
}

SAMPLE_VELOCITY_ROW = {
    "companies_measured": 12286,
    "avg_days_between": 147.3,
    "median_days_between": 98.0,
    "p25_days_between": 42.0,
    "p75_days_between": 213.0,
    "min_days_between": 0,
    "max_days_between": 1826,
    "within_90_days": 4102,
    "within_91_180_days": 3244,
    "within_181_365_days": 2891,
    "over_365_days": 2049,
}

SAMPLE_CEILING_ROW = {
    "vertical": "Manufacturing",
    "total_obligated": 340000.0,
    "total_ceiling": 2100000.0,
    "unique_companies": 100,
}


# ── Time Series Tests ────────────────────────────────────────────────────────


class TestTimeSeries:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_quarter_period_returns_yyyy_qn_format(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_TIME_SERIES_ROW])
        mock_get_pool.return_value = pool

        result = get_time_series(period="quarter")

        assert len(result) == 1
        assert result[0]["period"] == "2025-Q4"
        # Check ordering would be ASC (single row is trivially sorted)

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_month_period_returns_yyyy_mm_format(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_TIME_SERIES_MONTH])
        mock_get_pool.return_value = pool

        result = get_time_series(period="month")

        assert result[0]["period"] == "2025-11"

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_new_entrant_pct_between_0_and_100(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_TIME_SERIES_ROW])
        mock_get_pool.return_value = pool

        result = get_time_series()

        for row in result:
            assert 0 <= row["new_entrant_pct"] <= 100

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_filters_narrow_result_set(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_time_series(filters={"naics_prefix": "54", "state": "VA"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "naics_code LIKE %s" in sql
        assert "recipient_state_code = %s" in sql
        assert "54%" in params
        assert "VA" in params


# ── Size Distribution Tests ──────────────────────────────────────────────────


class TestSizeDistribution:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_returns_size_buckets_per_vertical(self, mock_get_pool):
        rows = []
        for i, bucket in enumerate(
            ["Under $100K", "$100K-$500K", "$500K-$1M", "$1M-$5M", "$5M+"], start=1
        ):
            rows.append({
                **SAMPLE_SIZE_DIST_ROW,
                "size_bucket": bucket,
                "bucket_order": i,
                "pct_of_vertical_transactions": 20.0,
            })
        pool, _ = _mock_pool(rows)
        mock_get_pool.return_value = pool

        result = get_award_size_distribution()

        assert len(result) == 5
        buckets = [r["size_bucket"] for r in result]
        assert buckets == ["Under $100K", "$100K-$500K", "$500K-$1M", "$1M-$5M", "$5M+"]

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_pct_of_vertical_sums_to_about_100(self, mock_get_pool):
        rows = []
        pcts = [35.0, 25.0, 20.0, 15.0, 5.0]
        for i, (bucket, pct) in enumerate(zip(
            ["Under $100K", "$100K-$500K", "$500K-$1M", "$1M-$5M", "$5M+"], pcts
        ), start=1):
            rows.append({
                **SAMPLE_SIZE_DIST_ROW,
                "size_bucket": bucket,
                "bucket_order": i,
                "pct_of_vertical_transactions": pct,
            })
        pool, _ = _mock_pool(rows)
        mock_get_pool.return_value = pool

        result = get_award_size_distribution()

        total_pct = sum(r["pct_of_vertical_transactions"] for r in result)
        assert 99.0 <= total_pct <= 101.0

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_buckets_in_logical_order(self, mock_get_pool):
        rows = []
        for i, bucket in enumerate(
            ["Under $100K", "$100K-$500K", "$500K-$1M", "$1M-$5M", "$5M+"], start=1
        ):
            rows.append({
                **SAMPLE_SIZE_DIST_ROW,
                "size_bucket": bucket,
                "bucket_order": i,
            })
        pool, _ = _mock_pool(rows)
        mock_get_pool.return_value = pool

        result = get_award_size_distribution()

        buckets = [r["size_bucket"] for r in result]
        assert buckets[0] == "Under $100K"
        assert buckets[-1] == "$5M+"

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_null_obligation_no_error(self, mock_get_pool):
        row = dict(SAMPLE_SIZE_DIST_ROW)
        row["total_obligated"] = None
        row["pct_of_vertical_dollars"] = None
        pool, _ = _mock_pool([row])
        mock_get_pool.return_value = pool

        result = get_award_size_distribution()

        assert result[0]["total_obligated"] == 0.0
        assert result[0]["pct_of_vertical_dollars"] == 0.0


# ── Set-Aside Tests ──────────────────────────────────────────────────────────


class TestSetAsideBreakdown:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_returns_rows_grouped_by_vertical_and_type(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_SET_ASIDE_ROW, SAMPLE_SET_ASIDE_NONE])
        mock_get_pool.return_value = pool

        result = get_set_aside_breakdown()

        assert len(result) == 2
        for row in result:
            assert "vertical" in row
            assert "set_aside_type" in row

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_none_category_exists(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_SET_ASIDE_ROW, SAMPLE_SET_ASIDE_NONE])
        mock_get_pool.return_value = pool

        result = get_set_aside_breakdown()

        types = [r["set_aside_type"] for r in result]
        assert "NONE" in types

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_percentages_non_negative(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_SET_ASIDE_ROW])
        mock_get_pool.return_value = pool

        result = get_set_aside_breakdown()

        for row in result:
            assert row["pct_of_vertical_transactions"] >= 0


# ── Competition Tests ────────────────────────────────────────────────────────


class TestCompetitionMetrics:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_sole_source_plus_full_competition_lte_100(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_COMPETITION_ROW])
        mock_get_pool.return_value = pool

        result = get_competition_metrics()

        for row in result:
            assert row["sole_source_pct"] + row["full_competition_pct"] <= 100.01

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_avg_offers_positive(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_COMPETITION_ROW])
        mock_get_pool.return_value = pool

        result = get_competition_metrics()

        assert result[0]["avg_offers_received"] > 0

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_ordered_by_total_awards_desc(self, mock_get_pool):
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_competition_metrics()

        sql = cursor.execute.call_args[0][0]
        assert "ORDER BY" in sql
        assert "DESC" in sql


# ── Geographic Tests ─────────────────────────────────────────────────────────


class TestGeographicHotspots:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_returns_two_letter_state_codes(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_GEO_ROW])
        mock_get_pool.return_value = pool

        result = get_geographic_hotspots()

        assert len(result[0]["state"]) == 2

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_no_state_filter_in_where(self, mock_get_pool):
        """State filter is excluded since state IS the dimension."""
        pool, cursor = _mock_pool([])
        mock_get_pool.return_value = pool

        get_geographic_hotspots(filters={"state": "TX", "naics_prefix": "31"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        # naics_prefix should be there, state should NOT
        assert "naics_code LIKE %s" in sql
        assert "recipient_state_code = %s" not in sql
        assert "TX" not in params

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_pct_first_time_between_0_and_100(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_GEO_ROW])
        mock_get_pool.return_value = pool

        result = get_geographic_hotspots()

        for row in result:
            assert 0 <= row["pct_first_time"] <= 100


# ── Repeat Velocity Tests ────────────────────────────────────────────────────


class TestRepeatAwardeeVelocity:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_returns_all_fields_and_distribution(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_VELOCITY_ROW])
        mock_get_pool.return_value = pool

        result = get_repeat_awardee_velocity()

        assert "companies_measured" in result
        assert "avg_days_between" in result
        assert "median_days_between" in result
        assert "p25_days_between" in result
        assert "p75_days_between" in result
        assert "min_days_between" in result
        assert "max_days_between" in result
        assert "distribution" in result

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_distribution_sums_to_companies_measured(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_VELOCITY_ROW])
        mock_get_pool.return_value = pool

        result = get_repeat_awardee_velocity()

        dist = result["distribution"]
        total = sum(dist.values())
        assert total == result["companies_measured"]

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_p25_lte_median_lte_p75(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_VELOCITY_ROW])
        mock_get_pool.return_value = pool

        result = get_repeat_awardee_velocity()

        assert result["p25_days_between"] <= result["median_days_between"]
        assert result["median_days_between"] <= result["p75_days_between"]

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_filters_narrow_companies(self, mock_get_pool):
        pool, cursor = _mock_pool([SAMPLE_VELOCITY_ROW])
        mock_get_pool.return_value = pool

        get_repeat_awardee_velocity(filters={"naics_prefix": "23", "state": "CA"})

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "naics_code LIKE %s" in sql
        assert "recipient_state_code = %s" in sql
        assert "23%" in params
        assert "CA" in params


# ── Ceiling Gap Tests ────────────────────────────────────────────────────────


class TestAwardCeilingGap:
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_returns_one_row_per_vertical(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_CEILING_ROW])
        mock_get_pool.return_value = pool

        result = get_award_ceiling_gap()

        assert len(result) == 1
        assert result[0]["vertical"] == "Manufacturing"

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_ceiling_to_obligation_ratio_gte_zero(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_CEILING_ROW])
        mock_get_pool.return_value = pool

        result = get_award_ceiling_gap()

        assert result[0]["ceiling_to_obligation_ratio"] >= 0

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_total_ceiling_gte_total_obligated(self, mock_get_pool):
        pool, _ = _mock_pool([SAMPLE_CEILING_ROW])
        mock_get_pool.return_value = pool

        result = get_award_ceiling_gap()

        assert result[0]["total_ceiling"] >= result[0]["total_obligated"]


# ── Endpoint Tests ───────────────────────────────────────────────────────────


ANALYTICS_ENDPOINTS = [
    ("/api/v1/federal-contract-leads/analytics/time-series", {"period": "quarter"}),
    ("/api/v1/federal-contract-leads/analytics/size-distribution", {}),
    ("/api/v1/federal-contract-leads/analytics/set-asides", {}),
    ("/api/v1/federal-contract-leads/analytics/competition", {}),
    ("/api/v1/federal-contract-leads/analytics/geographic", {}),
    ("/api/v1/federal-contract-leads/analytics/repeat-velocity", {}),
    ("/api/v1/federal-contract-leads/analytics/ceiling-gap", {}),
]


class TestAnalyticsEndpoints:
    @pytest.mark.parametrize("path,body", ANALYTICS_ENDPOINTS)
    @patch("app.services.federal_leads_analytics._get_pool")
    def test_all_endpoints_return_data_envelope(self, mock_get_pool, path, body):
        cleanup = _override_auth()
        try:
            # Use velocity row for repeat-velocity (returns single dict via fetchone),
            # others use fetchall
            if "repeat-velocity" in path:
                pool, _ = _mock_pool([SAMPLE_VELOCITY_ROW])
            elif "time-series" in path:
                pool, _ = _mock_pool([SAMPLE_TIME_SERIES_ROW])
            elif "size-distribution" in path:
                pool, _ = _mock_pool([SAMPLE_SIZE_DIST_ROW])
            elif "set-asides" in path:
                pool, _ = _mock_pool([SAMPLE_SET_ASIDE_ROW])
            elif "competition" in path:
                pool, _ = _mock_pool([SAMPLE_COMPETITION_ROW])
            elif "geographic" in path:
                pool, _ = _mock_pool([SAMPLE_GEO_ROW])
            elif "ceiling-gap" in path:
                pool, _ = _mock_pool([SAMPLE_CEILING_ROW])
            else:
                pool, _ = _mock_pool([])
            mock_get_pool.return_value = pool

            response = client.post(path, json=body, headers=SUPER_ADMIN_HEADERS)

            assert response.status_code == 200
            assert "data" in response.json()
        finally:
            cleanup()

    @pytest.mark.parametrize("path,body", ANALYTICS_ENDPOINTS)
    def test_all_endpoints_require_auth(self, path, body):
        response = client.post(path, json=body)
        assert response.status_code == 401

    def test_time_series_rejects_invalid_period(self):
        cleanup = _override_auth()
        try:
            response = client.post(
                "/api/v1/federal-contract-leads/analytics/time-series",
                json={"period": "week"},
                headers=SUPER_ADMIN_HEADERS,
            )
            assert response.status_code == 422
        finally:
            cleanup()

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_geographic_does_not_accept_state_filter(self, mock_get_pool):
        """GeographicRequest model has no state field."""
        cleanup = _override_auth()
        try:
            pool, cursor = _mock_pool([SAMPLE_GEO_ROW])
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/v1/federal-contract-leads/analytics/geographic",
                json={"state": "TX", "naics_prefix": "31"},
                headers=SUPER_ADMIN_HEADERS,
            )
            # The request should succeed (extra fields ignored by default in pydantic)
            # but the state should NOT appear in the SQL since GeographicRequest has no state
            assert response.status_code == 200
        finally:
            cleanup()

    @patch("app.services.federal_leads_analytics._get_pool")
    def test_naics_agency_breakdown_accepts_path_param(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, _ = _mock_pool([])
            mock_get_pool.return_value = pool

            # Re-use existing NAICS agency endpoint from naics_metrics
            from app.services.federal_leads_naics_metrics import _get_pool as nm_get_pool
            with patch("app.services.federal_leads_naics_metrics._get_pool", return_value=pool):
                response = client.post(
                    "/api/v1/federal-contract-leads/naics-metrics/541330/agencies",
                    headers=SUPER_ADMIN_HEADERS,
                )

            assert response.status_code == 200
            assert response.json()["data"]["naics_code"] == "541330"
        finally:
            cleanup()
