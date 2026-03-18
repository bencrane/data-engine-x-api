"""Tests for FMCSA Analytics — materialized view refresh, updated analytics services, and endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

INTERNAL_HEADERS = {"Authorization": "Bearer test-internal-key"}


def _mock_conn_pool():
    """Build mock pool -> connection -> cursor chain."""
    cursor = MagicMock()
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    conn = MagicMock()
    conn.cursor.return_value = cursor
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)

    pool = MagicMock()
    pool.connection.return_value = conn

    return pool, conn, cursor


# ── Refresh Service Tests ──────────────────────────────────────────────────


class TestRefreshAuthorityGrantsConcurrent:
    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_concurrent_true(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_fmcsa_authority_grants
        result = refresh_fmcsa_authority_grants(concurrent=True)

        sqls = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("CONCURRENTLY" in s for s in sqls)
        assert any("mv_fmcsa_authority_grants" in s for s in sqls)
        assert result["view"] == "mv_fmcsa_authority_grants"
        assert result["concurrent"] is True

    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_concurrent_false(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_fmcsa_authority_grants
        result = refresh_fmcsa_authority_grants(concurrent=False)

        sqls = [c[0][0] for c in cursor.execute.call_args_list]
        refresh_sql = [s for s in sqls if "REFRESH" in s][0]
        assert "CONCURRENTLY" not in refresh_sql
        assert result["concurrent"] is False


class TestRefreshInsuranceCancellations:
    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_concurrent_true(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_fmcsa_insurance_cancellations
        result = refresh_fmcsa_insurance_cancellations(concurrent=True)

        sqls = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("CONCURRENTLY" in s and "mv_fmcsa_insurance_cancellations" in s for s in sqls)
        assert result["view"] == "mv_fmcsa_insurance_cancellations"

    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_concurrent_false(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_fmcsa_insurance_cancellations
        result = refresh_fmcsa_insurance_cancellations(concurrent=False)

        sqls = [c[0][0] for c in cursor.execute.call_args_list]
        refresh_sql = [s for s in sqls if "REFRESH" in s][0]
        assert "CONCURRENTLY" not in refresh_sql


class TestRefreshAll:
    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_returns_combined_result(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_all_fmcsa_analytics
        result = refresh_all_fmcsa_analytics(concurrent=True)

        assert "authority_grants" in result
        assert "insurance_cancellations" in result
        assert "total_elapsed_ms" in result
        assert result["authority_grants"]["view"] == "mv_fmcsa_authority_grants"
        assert result["insurance_cancellations"]["view"] == "mv_fmcsa_insurance_cancellations"


class TestRefreshStatementTimeout:
    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_authority_grants_sets_timeout(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_fmcsa_authority_grants
        refresh_fmcsa_authority_grants()

        sqls = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("1800s" in s for s in sqls)

    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_insurance_cancellations_sets_timeout(self, mock_get_pool):
        pool, conn, cursor = _mock_conn_pool()
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics_refresh import refresh_fmcsa_insurance_cancellations
        refresh_fmcsa_insurance_cancellations()

        sqls = [c[0][0] for c in cursor.execute.call_args_list]
        assert any("1800s" in s for s in sqls)


# ── Updated Analytics Service Tests ────────────────────────────────────────


class TestFmcsaAnalyticsMVQueries:
    @patch("app.services.fmcsa_analytics._get_pool")
    def test_monthly_summary_queries_authority_grants_mv(self, mock_get_pool):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics import get_fmcsa_monthly_summary
        result = get_fmcsa_monthly_summary(months=6)

        sqls = [c[0][0] for c in cursor.execute.call_args_list if c[0]]
        authority_sql = [s for s in sqls if "authority" in s.lower()]
        assert len(authority_sql) == 1
        assert "mv_fmcsa_authority_grants" in authority_sql[0]
        assert "operating_authority_histories" not in authority_sql[0]

    @patch("app.services.fmcsa_analytics._get_pool")
    def test_monthly_summary_queries_insurance_cancellations_mv(self, mock_get_pool):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        from app.services.fmcsa_analytics import get_fmcsa_monthly_summary
        result = get_fmcsa_monthly_summary(months=6)

        sqls = [c[0][0] for c in cursor.execute.call_args_list if c[0]]
        cancel_sql = [s for s in sqls if "cancel" in s.lower()]
        assert len(cancel_sql) == 1
        assert "mv_fmcsa_insurance_cancellations" in cancel_sql[0]
        assert "insurance_policy_history_events" not in cancel_sql[0]


class TestConsolidatedAnalyticsMVQueries:
    @patch("app.services.fmcsa_consolidated_analytics._get_pool")
    def test_new_authorities_queries_mv(self, mock_get_pool):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        from app.services.fmcsa_consolidated_analytics import run_fmcsa_analytics
        result = run_fmcsa_analytics(query_type="new_authorities_by_month", params={"months": 6})

        sqls = [c[0][0] for c in cursor.execute.call_args_list if c[0]]
        authority_sql = [s for s in sqls if "authority" in s.lower() or "grant" in s.lower()]
        assert any("mv_fmcsa_authority_grants" in s for s in authority_sql)

    @patch("app.services.fmcsa_consolidated_analytics._get_pool")
    def test_insurance_cancellations_queries_mv_with_fallback(self, mock_get_pool):
        cursor = MagicMock()
        # Return empty on first call (primary MV), trigger fallback
        cursor.fetchall.side_effect = [[], []]
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn
        mock_get_pool.return_value = pool

        from app.services.fmcsa_consolidated_analytics import run_fmcsa_analytics
        result = run_fmcsa_analytics(query_type="insurance_cancellations_by_month", params={"months": 6})

        sqls = [c[0][0] for c in cursor.execute.call_args_list if c[0]]
        # First query should hit the MV
        cancel_sqls = [s for s in sqls if "cancel" in s.lower() or "insurance" in s.lower()]
        assert any("mv_fmcsa_insurance_cancellations" in s for s in cancel_sqls)
        # Fallback should hit fmcsa_carrier_signals
        assert any("fmcsa_carrier_signals" in s for s in sqls)
        assert result["source"] == "fmcsa_carrier_signals"


# ── Endpoint Tests ─────────────────────────────────────────────────────────


def _override_internal_auth():
    """Install dependency override for require_internal_key, return cleanup fn."""
    from app.routers.internal import require_internal_key
    app.dependency_overrides[require_internal_key] = lambda: None
    return lambda: app.dependency_overrides.pop(require_internal_key, None)


class TestFmcsaAnalyticsRefreshEndpoint:
    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_refresh_all_returns_data_envelope(self, mock_get_pool):
        cleanup = _override_internal_auth()
        try:
            pool, conn, cursor = _mock_conn_pool()
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/internal/fmcsa-analytics/refresh",
                json={"views": "all", "concurrent": True},
                headers=INTERNAL_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert "authority_grants" in body["data"]
            assert "insurance_cancellations" in body["data"]
            assert "total_elapsed_ms" in body["data"]
        finally:
            cleanup()

    @patch("app.services.fmcsa_analytics_refresh._get_pool")
    def test_refresh_authority_grants_only(self, mock_get_pool):
        cleanup = _override_internal_auth()
        try:
            pool, conn, cursor = _mock_conn_pool()
            mock_get_pool.return_value = pool

            response = client.post(
                "/api/internal/fmcsa-analytics/refresh",
                json={"views": "authority_grants"},
                headers=INTERNAL_HEADERS,
            )

            assert response.status_code == 200
            body = response.json()
            assert "data" in body
            assert body["data"]["view"] == "mv_fmcsa_authority_grants"
        finally:
            cleanup()

    def test_refresh_requires_auth(self):
        response = client.post(
            "/api/internal/fmcsa-analytics/refresh",
            json={"views": "all"},
        )
        assert response.status_code in (401, 403)
