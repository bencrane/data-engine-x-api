"""Tests for FMCSA signal query endpoints and services."""
from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────

SAMPLE_SIGNAL_ROW = {
    "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "signal_type": "new_carrier",
    "feed_date": datetime.date(2026, 3, 17),
    "detected_at": datetime.datetime(2026, 3, 17, 12, 0, 0),
    "dot_number": "12345",
    "docket_number": "MC-999999",
    "entity_key": "dot:12345",
    "severity": "info",
    "legal_name": "ACME TRUCKING LLC",
    "physical_state": "TX",
    "power_unit_count": 25,
    "driver_total": 30,
    "before_values": None,
    "after_values": {"power_unit_count": 25},
    "signal_details": {"note": "new entrant"},
    "source_table": "motor_carrier_census_records",
    "source_feed_name": "census_2026-03-17",
    "created_at": datetime.datetime(2026, 3, 17, 12, 0, 0),
}


def _make_row(**overrides):
    row = dict(SAMPLE_SIGNAL_ROW)
    row.update(overrides)
    return row


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


def _mock_pool_multi(call_rows: list[list[dict]]):
    """Pool that returns different rows on successive cursor.fetchall calls."""
    cursors = []
    for rows in call_rows:
        c = MagicMock()
        c.fetchall.return_value = [dict(r) for r in rows]
        c.fetchone.return_value = rows[0] if rows else None
        c.__enter__ = MagicMock(return_value=c)
        c.__exit__ = MagicMock(return_value=False)
        cursors.append(c)

    conn = MagicMock()
    conn.cursor.side_effect = cursors
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value = conn
    return pool


def _override_auth():
    from uuid import UUID
    from app.auth.models import SuperAdminContext
    from app.routers.fmcsa_v1 import _resolve_flexible_auth

    sa = SuperAdminContext(
        super_admin_id=UUID("00000000-0000-0000-0000-000000000001"),
        email="test@test.com",
    )
    app.dependency_overrides[_resolve_flexible_auth] = lambda: sa
    return lambda: app.dependency_overrides.pop(_resolve_flexible_auth, None)


# ── 1. Query Service Tests ────────────────────────────────────────────────


class TestQueryFmcsaSignals:

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_no_filters_returns_paginated(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        row = _make_row(total_matched=3)
        pool, _ = _mock_pool([row])
        mock_get_pool.return_value = pool

        result = query_fmcsa_signals(filters={}, limit=25, offset=0)

        assert result["limit"] == 25
        assert result["offset"] == 0
        assert result["total_matched"] == 3
        assert len(result["items"]) == 1
        assert "total_matched" not in result["items"][0]

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_signal_type_filter(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        row = _make_row(signal_type="new_carrier", total_matched=1)
        pool, cursor = _mock_pool([row])
        mock_get_pool.return_value = pool

        result = query_fmcsa_signals(
            filters={"signal_type": "new_carrier"}, limit=25, offset=0
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "signal_type = %s" in sql
        assert "new_carrier" in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_signal_types_list_filter(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        pool, cursor = _mock_pool([_make_row(total_matched=2)])
        mock_get_pool.return_value = pool

        query_fmcsa_signals(
            filters={"signal_types": ["new_carrier", "new_crash"]},
            limit=25,
            offset=0,
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "signal_type IN (%s, %s)" in sql
        assert "new_carrier" in params
        assert "new_crash" in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_min_severity_warning(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        pool, cursor = _mock_pool([_make_row(total_matched=1)])
        mock_get_pool.return_value = pool

        query_fmcsa_signals(
            filters={"min_severity": "warning"}, limit=25, offset=0
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "severity IN (%s, %s)" in sql
        assert "warning" in params
        assert "critical" in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_date_range_filter(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        pool, cursor = _mock_pool([_make_row(total_matched=1)])
        mock_get_pool.return_value = pool

        query_fmcsa_signals(
            filters={"feed_date_from": "2026-03-01", "feed_date_to": "2026-03-17"},
            limit=25,
            offset=0,
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "feed_date >= %s::DATE" in sql
        assert "feed_date <= %s::DATE" in sql
        assert "2026-03-01" in params
        assert "2026-03-17" in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_min_power_units_filter(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        pool, cursor = _mock_pool([_make_row(total_matched=1)])
        mock_get_pool.return_value = pool

        query_fmcsa_signals(
            filters={"min_power_units": 10}, limit=25, offset=0
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "power_unit_count >= %s" in sql
        assert 10 in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_legal_name_contains_filter(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        pool, cursor = _mock_pool([_make_row(total_matched=1)])
        mock_get_pool.return_value = pool

        query_fmcsa_signals(
            filters={"legal_name_contains": "ACME"}, limit=25, offset=0
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "legal_name ILIKE %s" in sql
        assert "%ACME%" in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_state_filter(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_fmcsa_signals

        pool, cursor = _mock_pool([_make_row(total_matched=1)])
        mock_get_pool.return_value = pool

        query_fmcsa_signals(
            filters={"state": "TX"}, limit=25, offset=0
        )

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "physical_state = %s" in sql
        assert "TX" in params


class TestGetFmcsaSignalSummary:

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_all_9_signal_types_present(self, mock_get_pool):
        from app.services.fmcsa_signal_query import get_fmcsa_signal_summary, ALL_SIGNAL_TYPES

        # Return only 2 types from DB
        pool = _mock_pool_multi([
            # First call: MAX(feed_date)
            [{"max_date": datetime.date(2026, 3, 17)}],
            # Second call: GROUP BY
            [
                {"signal_type": "new_carrier", "severity": "info", "cnt": 5},
                {"signal_type": "new_crash", "severity": "critical", "cnt": 2},
            ],
        ])
        mock_get_pool.return_value = pool

        result = get_fmcsa_signal_summary(filters={})

        assert len(result["by_type"]) == 9
        for st in ALL_SIGNAL_TYPES:
            assert st in result["by_type"]
            assert "count" in result["by_type"][st]
            assert "critical" in result["by_type"][st]
            assert "warning" in result["by_type"][st]
            assert "info" in result["by_type"][st]

        assert result["by_type"]["new_carrier"]["info"] == 5
        assert result["by_type"]["new_carrier"]["count"] == 5
        assert result["by_type"]["new_crash"]["critical"] == 2
        assert result["by_type"]["disappeared_carrier"]["count"] == 0

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_auto_detects_latest_feed_date(self, mock_get_pool):
        from app.services.fmcsa_signal_query import get_fmcsa_signal_summary

        pool = _mock_pool_multi([
            [{"max_date": datetime.date(2026, 3, 15)}],
            [],
        ])
        mock_get_pool.return_value = pool

        result = get_fmcsa_signal_summary(filters={})
        assert result["feed_date"] == "2026-03-15"

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_no_data_returns_all_zeros(self, mock_get_pool):
        from app.services.fmcsa_signal_query import get_fmcsa_signal_summary

        pool = _mock_pool_multi([
            [{"max_date": None}],  # no data
        ])
        mock_get_pool.return_value = pool

        result = get_fmcsa_signal_summary(filters={})
        assert result["feed_date"] is None
        assert result["total_signals"] == 0
        assert result["by_severity"]["critical"] == 0

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_state_filter_scoped(self, mock_get_pool):
        from app.services.fmcsa_signal_query import get_fmcsa_signal_summary

        pool = _mock_pool_multi([
            [{"max_date": datetime.date(2026, 3, 17)}],
            [{"signal_type": "new_carrier", "severity": "info", "cnt": 3}],
        ])
        mock_get_pool.return_value = pool

        result = get_fmcsa_signal_summary(filters={"state": "TX"})
        assert result["total_signals"] == 3


class TestQueryCarrierSignals:

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_filters_by_dot_number(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_carrier_signals

        row = _make_row(dot_number="12345", total_matched=1)
        pool, cursor = _mock_pool([row])
        mock_get_pool.return_value = pool

        result = query_carrier_signals(
            dot_number="12345", filters={}, limit=50, offset=0
        )

        assert result["dot_number"] == "12345"
        assert result["total_matched"] == 1
        assert len(result["items"]) == 1

        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        assert "dot_number = %s" in sql
        assert "12345" in params

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_no_signals_returns_empty(self, mock_get_pool):
        from app.services.fmcsa_signal_query import query_carrier_signals

        pool, _ = _mock_pool([])
        mock_get_pool.return_value = pool

        result = query_carrier_signals(
            dot_number="99999", filters={}, limit=50, offset=0
        )

        assert result["dot_number"] == "99999"
        assert result["items"] == []
        assert result["total_matched"] == 0


# ── 2. Filter Building Tests ──────────────────────────────────────────────


class TestFilterBuilding:

    def test_min_severity_warning_produces_in_clause(self):
        from app.services.fmcsa_signal_query import _build_signal_where

        conditions, params = _build_signal_where({"min_severity": "warning"})
        joined = " ".join(conditions)
        assert "severity IN (%s, %s)" in joined
        assert "warning" in params
        assert "critical" in params

    def test_min_severity_critical_produces_exact_match(self):
        from app.services.fmcsa_signal_query import _build_signal_where

        conditions, params = _build_signal_where({"min_severity": "critical"})
        joined = " ".join(conditions)
        assert "severity = %s" in joined
        assert "critical" in params
        assert "warning" not in params

    def test_signal_types_list_produces_in_clause(self):
        from app.services.fmcsa_signal_query import _build_signal_where

        conditions, params = _build_signal_where(
            {"signal_types": ["new_carrier", "insurance_lapsed", "new_crash"]}
        )
        joined = " ".join(conditions)
        assert "signal_type IN (%s, %s, %s)" in joined
        assert params[:3] == ["new_carrier", "insurance_lapsed", "new_crash"]

    def test_signal_types_overrides_signal_type(self):
        from app.services.fmcsa_signal_query import _build_signal_where

        conditions, params = _build_signal_where(
            {"signal_type": "new_carrier", "signal_types": ["new_crash"]}
        )
        joined = " ".join(conditions)
        # signal_types wins — should use IN, not =
        assert "signal_type IN (%s)" in joined
        assert "new_crash" in params
        assert "signal_type = %s" not in joined

    def test_all_params_are_parameterized(self):
        from app.services.fmcsa_signal_query import _build_signal_where

        conditions, params = _build_signal_where({
            "signal_type": "new_carrier",
            "severity": "critical",
            "dot_number": "12345",
            "state": "TX",
            "feed_date": "2026-03-17",
            "feed_date_from": "2026-03-01",
            "feed_date_to": "2026-03-17",
            "min_power_units": 5,
            "legal_name_contains": "ACME",
        })
        # No string interpolation of values — all values are in params
        for cond in conditions:
            assert "%s" in cond
        assert len(params) >= 8


# ── 3. Endpoint Tests (via TestClient) ────────────────────────────────────


class TestSignalQueryEndpoint:

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_post_query_with_auth_returns_200(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            row = _make_row(total_matched=1)
            pool, _ = _mock_pool([row])
            mock_get_pool.return_value = pool

            resp = client.post(
                "/api/v1/fmcsa-signals/query",
                json={"limit": 10},
                headers={"Authorization": "Bearer fake"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "data" in body
            assert "items" in body["data"]
            assert "total_matched" in body["data"]
        finally:
            cleanup()

    def test_post_query_without_auth_returns_401(self):
        resp = client.post("/api/v1/fmcsa-signals/query", json={})
        assert resp.status_code == 401


class TestSignalSummaryEndpoint:

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_get_summary_returns_200(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool = _mock_pool_multi([
                [{"max_date": datetime.date(2026, 3, 17)}],
                [{"signal_type": "new_carrier", "severity": "info", "cnt": 5}],
            ])
            mock_get_pool.return_value = pool

            resp = client.get(
                "/api/v1/fmcsa-signals/summary",
                headers={"Authorization": "Bearer fake"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "data" in body
            assert "by_type" in body["data"]
            assert "by_severity" in body["data"]
            assert len(body["data"]["by_type"]) == 9
        finally:
            cleanup()


class TestCarrierSignalsEndpoint:

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_get_carrier_signals_returns_200(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            row = _make_row(dot_number="12345", total_matched=1)
            pool, _ = _mock_pool([row])
            mock_get_pool.return_value = pool

            resp = client.get(
                "/api/v1/fmcsa-carriers/12345/signals",
                headers={"Authorization": "Bearer fake"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert "data" in body
            assert body["data"]["dot_number"] == "12345"
            assert "items" in body["data"]
        finally:
            cleanup()

    @patch("app.services.fmcsa_signal_query._get_pool")
    def test_no_signals_returns_empty_not_404(self, mock_get_pool):
        cleanup = _override_auth()
        try:
            pool, _ = _mock_pool([])
            mock_get_pool.return_value = pool

            resp = client.get(
                "/api/v1/fmcsa-carriers/99999/signals",
                headers={"Authorization": "Bearer fake"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["data"]["items"] == []
            assert body["data"]["total_matched"] == 0
        finally:
            cleanup()
