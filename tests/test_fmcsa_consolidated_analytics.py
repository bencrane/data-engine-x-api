"""Tests for FMCSA consolidated analytics — new authorities, insurance cancellations."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.fmcsa_consolidated_analytics import run_fmcsa_analytics

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


def _override_fmcsa_auth():
    from app.routers.fmcsa_v1 import _resolve_flexible_auth
    sa = _make_super_admin()
    app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
    return lambda: app.dependency_overrides.pop(_resolve_flexible_auth, None)


POOL_PATH = "app.services.fmcsa_consolidated_analytics._get_pool"


# ── Sample rows ──────────────────────────────────────────────────────────────

SAMPLE_AUTH_ROW = {
    "month": "2025-10",
    "new_authorities": 415,
    "unique_carriers": 371,
}

SAMPLE_CANCEL_ROW = {
    "month": "2025-09",
    "cancellations": 1203,
    "unique_carriers": 987,
}


# ── Query Type 1: new_authorities_by_month ───────────────────────────────────


class TestNewAuthoritiesByMonth:
    def test_returns_all_fields(self):
        pool, _ = _mock_pool([SAMPLE_AUTH_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_fmcsa_analytics(
                query_type="new_authorities_by_month",
                params={"months": 6},
            )
        assert result["query_type"] == "new_authorities_by_month"
        item = result["items"][0]
        assert "month" in item
        assert "new_authorities" in item
        assert "unique_carriers" in item
        # Verify month format
        assert len(item["month"]) == 7  # YYYY-MM

    def test_months_controls_range(self):
        pool, cursor = _mock_pool([SAMPLE_AUTH_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_fmcsa_analytics(
                query_type="new_authorities_by_month",
                params={"months": 3},
            )
        # Verify date_range reflects months=3 (approx 93 days back)
        assert "date_range" in result
        assert result["date_range"]["from"] < result["date_range"]["to"]

    def test_date_from_to_override(self):
        pool, cursor = _mock_pool([SAMPLE_AUTH_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_fmcsa_analytics(
                query_type="new_authorities_by_month",
                params={"date_from": "2025-06-01", "date_to": "2025-12-31"},
            )
        assert result["date_range"]["from"] == "2025-06-01"
        assert result["date_range"]["to"] == "2025-12-31"


# ── Query Type 2: insurance_cancellations_by_month ───────────────────────────


class TestInsuranceCancellationsByMonth:
    def test_returns_all_fields(self):
        pool, _ = _mock_pool([SAMPLE_CANCEL_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_fmcsa_analytics(
                query_type="insurance_cancellations_by_month",
                params={"months": 6},
            )
        assert result["query_type"] == "insurance_cancellations_by_month"
        item = result["items"][0]
        assert "month" in item
        assert "cancellations" in item
        assert "unique_carriers" in item

    def test_includes_source_field(self):
        pool, _ = _mock_pool([SAMPLE_CANCEL_ROW])
        with patch(POOL_PATH, return_value=pool):
            result = run_fmcsa_analytics(
                query_type="insurance_cancellations_by_month",
                params={"months": 6},
            )
        assert result["source"] == "insurance_policy_history_events"

    def test_falls_back_to_signals(self):
        """When primary returns empty, falls back to fmcsa_carrier_signals."""
        cursor = MagicMock()
        # First call: SET statement_timeout
        # Second call: primary query returns []
        # Third call: RESET
        # Fourth call: SET statement_timeout
        # Fifth call: fallback query returns rows
        # Sixth call: RESET
        cursor.fetchall.side_effect = [[], [dict(SAMPLE_CANCEL_ROW)]]
        cursor.__enter__ = MagicMock(return_value=cursor)
        cursor.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor
        conn.__enter__ = MagicMock(return_value=conn)
        conn.__exit__ = MagicMock(return_value=False)

        pool = MagicMock()
        pool.connection.return_value = conn

        with patch(POOL_PATH, return_value=pool):
            result = run_fmcsa_analytics(
                query_type="insurance_cancellations_by_month",
                params={"months": 6},
            )
        assert result["source"] == "fmcsa_carrier_signals"
        assert len(result["items"]) == 1


# ── Unknown query type ──────────────────────────────────────────────────────


def test_unknown_query_type():
    with pytest.raises(ValueError, match="Unknown query_type"):
        run_fmcsa_analytics(query_type="nonexistent")


# ── Endpoint tests ──────────────────────────────────────────────────────────


class TestFmcsaAnalyticsEndpoint:
    def test_returns_data_envelope(self):
        cleanup = _override_fmcsa_auth()
        try:
            pool, _ = _mock_pool([SAMPLE_AUTH_ROW])
            with patch(POOL_PATH, return_value=pool):
                resp = client.post(
                    "/api/v1/fmcsa-carriers/analytics",
                    json={"query_type": "new_authorities_by_month", "months": 6},
                )
            assert resp.status_code == 200
            body = resp.json()
            assert "data" in body
            assert body["data"]["query_type"] == "new_authorities_by_month"
        finally:
            cleanup()

    def test_auth_required(self):
        resp = client.post(
            "/api/v1/fmcsa-carriers/analytics",
            json={"query_type": "new_authorities_by_month"},
        )
        assert resp.status_code in (401, 403)
