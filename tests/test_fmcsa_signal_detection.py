"""Tests for FMCSA Signal Detection Engine."""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.fmcsa_signal_detection import (
    detect_new_carriers,
    detect_disappeared_carriers,
    detect_authority_granted,
    detect_authority_revoked,
    detect_insurance_added,
    detect_insurance_lapsed,
    detect_safety_worsened,
    detect_new_crashes,
    detect_new_oos_orders,
    enrich_carriers,
    resolve_docket_to_dot,
    run_signal_detection,
)


# ---------------------------------------------------------------------------
# Helpers for building mock pool + cursor
# ---------------------------------------------------------------------------


def _make_pool(query_results: list[list[dict[str, Any]]]) -> MagicMock:
    """Create a mock connection pool that returns successive query results."""
    pool = MagicMock()
    cursor = MagicMock()
    conn = MagicMock()

    call_idx = {"i": 0}

    def _fetchall():
        idx = call_idx["i"]
        call_idx["i"] += 1
        if idx < len(query_results):
            return query_results[idx]
        return []

    def _fetchone():
        idx = call_idx["i"]
        call_idx["i"] += 1
        if idx < len(query_results) and query_results[idx]:
            return query_results[idx][0]
        return None

    cursor.fetchall = _fetchall
    cursor.fetchone = _fetchone
    cursor.execute = MagicMock()
    cursor.rowcount = 1
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)
    conn.cursor = MagicMock(return_value=cursor)
    conn.commit = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    pool.connection = MagicMock(return_value=conn)
    return pool


# ---------------------------------------------------------------------------
# Detection Function Tests
# ---------------------------------------------------------------------------


class TestDetectNewCarriers:
    def test_returns_new_carriers(self):
        # Query 1: two feed dates
        # Query 2: today's carriers minus yesterday's
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "dot_number": "12345",
                    "carrier_operation_code": "A",
                    "physical_state": "TX",
                    "power_unit_count": 10,
                    "driver_total": 5,
                    "source_feed_name": "census_daily",
                },
            ],
        ])
        signals = detect_new_carriers("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "new_carrier"
        assert signals[0]["entity_key"] == "12345"
        assert signals[0]["severity"] == "info"
        assert signals[0]["after_values"]["physical_state"] == "TX"

    def test_no_signals_when_single_snapshot(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}],
        ])
        assert detect_new_carriers("2026-03-17", pool) == []


class TestDetectDisappearedCarriers:
    def test_returns_disappeared_carriers(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "dot_number": "99999",
                    "carrier_operation_code": "B",
                    "physical_state": "CA",
                    "power_unit_count": 50,
                    "driver_total": 30,
                    "source_feed_name": "census_daily",
                },
            ],
        ])
        signals = detect_disappeared_carriers("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "disappeared_carrier"
        assert signals[0]["severity"] == "warning"
        assert signals[0]["before_values"]["physical_state"] == "CA"


class TestDetectAuthorityGranted:
    def test_returns_granted_authority(self):
        pool = _make_pool([
            [
                {"source_observed_at": datetime(2026, 3, 17, 12, 0)},
                {"source_observed_at": datetime(2026, 3, 16, 12, 0)},
            ],
            [
                {
                    "record_fingerprint": "fp-auth-001",
                    "usdot_number": "11111",
                    "docket_number": "MC-1234",
                    "operating_authority_type": "Common",
                    "original_authority_action_description": "GRANT OF AUTHORITY",
                    "final_authority_action_description": "GRANT OF AUTHORITY",
                    "final_authority_decision_date": date(2026, 3, 17),
                    "final_authority_served_date": date(2026, 3, 17),
                    "source_feed_name": "authority_history",
                },
            ],
        ])
        signals = detect_authority_granted("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "authority_granted"
        assert signals[0]["dot_number"] == "11111"
        assert signals[0]["entity_key"] == "fp-auth-001"
        assert signals[0]["severity"] == "info"


class TestDetectAuthorityRevoked:
    def test_returns_revoked_authority(self):
        pool = _make_pool([
            [
                {"source_observed_at": datetime(2026, 3, 17, 12, 0)},
                {"source_observed_at": datetime(2026, 3, 16, 12, 0)},
            ],
            [
                {
                    "record_fingerprint": "fp-rev-001",
                    "usdot_number": "22222",
                    "docket_number": "MC-5678",
                    "operating_authority_registration_type": "Common",
                    "revocation_type": "Involuntary",
                    "serve_date": date(2026, 3, 10),
                    "effective_date": date(2026, 3, 17),
                    "source_feed_name": "revocations",
                },
            ],
        ])
        signals = detect_authority_revoked("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "authority_revoked"
        assert signals[0]["severity"] == "warning"
        assert signals[0]["dot_number"] == "22222"


class TestDetectInsuranceAdded:
    def test_returns_new_insurance_with_docket_resolution(self):
        pool = _make_pool([
            # Two observation windows
            [
                {"source_observed_at": datetime(2026, 3, 17, 12, 0)},
                {"source_observed_at": datetime(2026, 3, 16, 12, 0)},
            ],
            # New insurance records
            [
                {
                    "record_fingerprint": "fp-ins-001",
                    "docket_number": "MC-9999",
                    "insurance_type_code": "BIPD",
                    "insurance_type_description": "Bodily Injury & Property Damage",
                    "bipd_maximum_dollar_limit_thousands_usd": 750,
                    "policy_number": "POL-123",
                    "effective_date": date(2026, 3, 1),
                    "insurance_company_name": "Acme Insurance",
                    "source_feed_name": "insurance_active",
                },
            ],
            # Docket-to-DOT resolution (resolve_docket_to_dot query)
            [
                {"docket_number": "MC-9999", "usdot_number": "33333"},
            ],
        ])
        signals = detect_insurance_added("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "insurance_added"
        assert signals[0]["dot_number"] == "33333"
        assert signals[0]["severity"] == "info"


class TestDetectInsuranceLapsed:
    def test_returns_lapsed_insurance_bipd_critical(self):
        pool = _make_pool([
            [
                {"source_observed_at": datetime(2026, 3, 17, 12, 0)},
                {"source_observed_at": datetime(2026, 3, 16, 12, 0)},
            ],
            [
                {
                    "record_fingerprint": "fp-ins-lapsed-001",
                    "docket_number": "MC-4444",
                    "insurance_type_code": "BIPD",
                    "insurance_type_description": "Bodily Injury & Property Damage",
                    "bipd_maximum_dollar_limit_thousands_usd": 750,
                    "policy_number": "POL-456",
                    "effective_date": date(2025, 1, 1),
                    "insurance_company_name": "SafeGuard Insurance",
                    "is_removal_signal": True,
                    "source_feed_name": "insurance_active",
                },
            ],
            # Docket-to-DOT resolution
            [
                {"docket_number": "MC-4444", "usdot_number": "44444"},
            ],
        ])
        signals = detect_insurance_lapsed("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "insurance_lapsed"
        assert signals[0]["severity"] == "critical"  # BIPD coverage
        assert signals[0]["dot_number"] == "44444"

    def test_non_bipd_insurance_lapsed_is_warning(self):
        pool = _make_pool([
            [
                {"source_observed_at": datetime(2026, 3, 17, 12, 0)},
                {"source_observed_at": datetime(2026, 3, 16, 12, 0)},
            ],
            [
                {
                    "record_fingerprint": "fp-ins-lapsed-002",
                    "docket_number": "MC-5555",
                    "insurance_type_code": "CARGO",
                    "insurance_type_description": "Cargo",
                    "bipd_maximum_dollar_limit_thousands_usd": None,
                    "policy_number": "POL-789",
                    "effective_date": date(2025, 6, 1),
                    "insurance_company_name": "Cargo Corp",
                    "is_removal_signal": True,
                    "source_feed_name": "insurance_active",
                },
            ],
            [
                {"docket_number": "MC-5555", "usdot_number": "55555"},
            ],
        ])
        signals = detect_insurance_lapsed("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["severity"] == "warning"


class TestDetectSafetyWorsened:
    def test_threshold_crossing_75(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "dot_number": "CARRIER_X",
                    "source_feed_name": "sms_percentiles",
                    "today_unsafe_driving_percentile": Decimal("80"),
                    "yesterday_unsafe_driving_percentile": Decimal("70"),
                    "today_hours_of_service_percentile": Decimal("50"),
                    "yesterday_hours_of_service_percentile": Decimal("50"),
                    "today_driver_fitness_percentile": Decimal("30"),
                    "yesterday_driver_fitness_percentile": Decimal("30"),
                    "today_controlled_substances_alcohol_percentile": Decimal("20"),
                    "yesterday_controlled_substances_alcohol_percentile": Decimal("20"),
                    "today_vehicle_maintenance_percentile": Decimal("40"),
                    "yesterday_vehicle_maintenance_percentile": Decimal("40"),
                },
            ],
        ])
        signals = detect_safety_worsened("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["severity"] == "warning"
        worsened = signals[0]["signal_details"]["worsened_basics"]
        assert len(worsened) == 1
        assert worsened[0]["basic"] == "unsafe_driving"
        assert worsened[0]["threshold_crossed"] == 75

    def test_no_signal_when_no_threshold_crossed(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "dot_number": "CARRIER_Y",
                    "source_feed_name": "sms_percentiles",
                    "today_unsafe_driving_percentile": Decimal("74"),
                    "yesterday_unsafe_driving_percentile": Decimal("74"),
                    "today_hours_of_service_percentile": Decimal("50"),
                    "yesterday_hours_of_service_percentile": Decimal("50"),
                    "today_driver_fitness_percentile": Decimal("30"),
                    "yesterday_driver_fitness_percentile": Decimal("30"),
                    "today_controlled_substances_alcohol_percentile": Decimal("20"),
                    "yesterday_controlled_substances_alcohol_percentile": Decimal("20"),
                    "today_vehicle_maintenance_percentile": Decimal("40"),
                    "yesterday_vehicle_maintenance_percentile": Decimal("40"),
                },
            ],
        ])
        signals = detect_safety_worsened("2026-03-17", pool)
        assert len(signals) == 0

    def test_threshold_crossing_90_is_critical(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "dot_number": "CARRIER_Z",
                    "source_feed_name": "sms_percentiles",
                    "today_unsafe_driving_percentile": Decimal("91"),
                    "yesterday_unsafe_driving_percentile": Decimal("89"),
                    "today_hours_of_service_percentile": Decimal("50"),
                    "yesterday_hours_of_service_percentile": Decimal("50"),
                    "today_driver_fitness_percentile": Decimal("30"),
                    "yesterday_driver_fitness_percentile": Decimal("30"),
                    "today_controlled_substances_alcohol_percentile": Decimal("20"),
                    "yesterday_controlled_substances_alcohol_percentile": Decimal("20"),
                    "today_vehicle_maintenance_percentile": Decimal("40"),
                    "yesterday_vehicle_maintenance_percentile": Decimal("40"),
                },
            ],
        ])
        signals = detect_safety_worsened("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["severity"] == "critical"
        worsened = signals[0]["signal_details"]["worsened_basics"]
        assert worsened[0]["threshold_crossed"] == 90


class TestDetectNewCrashes:
    def test_returns_new_crashes(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "crash_id": "CR-001",
                    "dot_number": "66666",
                    "report_date": date(2026, 3, 15),
                    "state": "FL",
                    "city": "Miami",
                    "fatalities": 0,
                    "injuries": 2,
                    "tow_away": True,
                    "hazmat_released": False,
                    "source_feed_name": "crashes",
                },
            ],
        ])
        signals = detect_new_crashes("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "new_crash"
        assert signals[0]["severity"] == "warning"  # no fatalities
        assert signals[0]["entity_key"] == "CR-001"

    def test_fatal_crash_is_critical(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "crash_id": "CR-002",
                    "dot_number": "77777",
                    "report_date": date(2026, 3, 14),
                    "state": "TX",
                    "city": "Houston",
                    "fatalities": 1,
                    "injuries": 3,
                    "tow_away": True,
                    "hazmat_released": False,
                    "source_feed_name": "crashes",
                },
            ],
        ])
        signals = detect_new_crashes("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["severity"] == "critical"


class TestDetectNewOosOrders:
    def test_returns_new_oos_orders(self):
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}, {"feed_date": date(2026, 3, 16)}],
            [
                {
                    "dot_number": "88888",
                    "oos_date": date(2026, 3, 16),
                    "oos_reason": "Unsatisfactory Safety Rating",
                    "status": "Active",
                    "source_feed_name": "oos_orders",
                },
            ],
        ])
        signals = detect_new_oos_orders("2026-03-17", pool)
        assert len(signals) == 1
        assert signals[0]["signal_type"] == "new_oos_order"
        assert signals[0]["severity"] == "critical"
        assert signals[0]["entity_key"] == "88888:2026-03-16"


# ---------------------------------------------------------------------------
# Enrichment Tests
# ---------------------------------------------------------------------------


class TestEnrichCarriers:
    def test_returns_census_fields(self):
        pool = _make_pool([
            [
                {
                    "dot_number": "12345",
                    "legal_name": "Acme Trucking",
                    "physical_state": "TX",
                    "power_unit_count": 10,
                    "driver_total": 5,
                },
            ],
        ])
        result = enrich_carriers(pool, ["12345"])
        assert "12345" in result
        assert result["12345"]["legal_name"] == "Acme Trucking"

    def test_returns_empty_for_unknown(self):
        pool = _make_pool([[]])
        result = enrich_carriers(pool, ["UNKNOWN_DOT"])
        assert "UNKNOWN_DOT" not in result

    def test_returns_empty_for_empty_input(self):
        pool = _make_pool([])
        result = enrich_carriers(pool, [])
        assert result == {}


class TestResolveDocketToDot:
    def test_resolves_known_docket(self):
        pool = _make_pool([
            [{"docket_number": "MC-1234", "usdot_number": "56789"}],
        ])
        result = resolve_docket_to_dot(pool, ["MC-1234"])
        assert result == {"MC-1234": "56789"}

    def test_skips_unknown_docket(self):
        pool = _make_pool([[]])
        result = resolve_docket_to_dot(pool, ["MC-UNKNOWN"])
        assert result == {}

    def test_returns_empty_for_empty_input(self):
        pool = _make_pool([])
        result = resolve_docket_to_dot(pool, [])
        assert result == {}


# ---------------------------------------------------------------------------
# Orchestrator Tests
# ---------------------------------------------------------------------------


class TestRunSignalDetection:
    @patch("app.services.fmcsa_signal_detection._get_pool")
    @patch("app.services.fmcsa_signal_detection._persist_signals")
    @patch("app.services.fmcsa_signal_detection.enrich_carriers")
    def test_calls_all_detectors_and_returns_summary(
        self, mock_enrich, mock_persist, mock_get_pool
    ):
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        mock_enrich.return_value = {}
        mock_persist.return_value = 0

        with patch("app.services.fmcsa_signal_detection.ALL_DETECTORS", []):
            result = run_signal_detection("2026-03-17")

        assert result["feed_date"] == "2026-03-17"
        assert result["total_signals"] == 0
        assert isinstance(result["counts"], dict)

    @patch("app.services.fmcsa_signal_detection._get_pool")
    @patch("app.services.fmcsa_signal_detection._persist_signals")
    @patch("app.services.fmcsa_signal_detection.enrich_carriers")
    def test_accumulates_counts_from_detectors(
        self, mock_enrich, mock_persist, mock_get_pool
    ):
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        mock_enrich.return_value = {}
        mock_persist.return_value = 3

        def fake_detector(feed_date, pool):
            return [
                {"signal_type": "test", "dot_number": "1", "entity_key": "1",
                 "feed_date": feed_date, "source_table": "t", "source_feed_name": "f",
                 "severity": "info"},
                {"signal_type": "test", "dot_number": "2", "entity_key": "2",
                 "feed_date": feed_date, "source_table": "t", "source_feed_name": "f",
                 "severity": "info"},
                {"signal_type": "test", "dot_number": "3", "entity_key": "3",
                 "feed_date": feed_date, "source_table": "t", "source_feed_name": "f",
                 "severity": "info"},
            ]

        fake_detector.__name__ = "detect_fake_signal"

        with patch("app.services.fmcsa_signal_detection.ALL_DETECTORS", [fake_detector]):
            result = run_signal_detection("2026-03-17")

        assert result["total_signals"] == 3
        assert result["counts"]["fake_signal"] == 3

    @patch("app.services.fmcsa_signal_detection._get_pool")
    @patch("app.services.fmcsa_signal_detection._persist_signals")
    @patch("app.services.fmcsa_signal_detection.enrich_carriers")
    def test_idempotency_second_run_inserts_zero(
        self, mock_enrich, mock_persist, mock_get_pool
    ):
        mock_pool = MagicMock()
        mock_get_pool.return_value = mock_pool
        mock_enrich.return_value = {}
        # Second run: ON CONFLICT DO NOTHING means 0 inserted
        mock_persist.return_value = 0

        def fake_detector(feed_date, pool):
            return [{"signal_type": "test", "dot_number": "1", "entity_key": "1",
                     "feed_date": feed_date, "source_table": "t", "source_feed_name": "f",
                     "severity": "info"}]

        fake_detector.__name__ = "detect_fake_signal"

        with patch("app.services.fmcsa_signal_detection.ALL_DETECTORS", [fake_detector]):
            result = run_signal_detection("2026-03-17")

        assert result["total_signals"] == 0

    @patch("app.services.fmcsa_signal_detection._get_pool")
    def test_graceful_skip_single_snapshot(self, mock_get_pool):
        """If a table has only one snapshot, that detector returns 0 signals."""
        pool = _make_pool([
            [{"feed_date": date(2026, 3, 17)}],  # only one feed_date
        ])
        mock_get_pool.return_value = pool

        signals = detect_new_carriers("2026-03-17", pool)
        assert signals == []


# ---------------------------------------------------------------------------
# Endpoint Tests
# ---------------------------------------------------------------------------


class TestDetectEndpoint:
    @patch("app.services.fmcsa_signal_detection.run_signal_detection")
    def test_detect_endpoint_returns_200(self, mock_run):
        mock_run.return_value = {
            "feed_date": "2026-03-17",
            "total_signals": 5,
            "counts": {"new_carrier": 3, "new_crash": 2},
        }
        from fastapi.testclient import TestClient
        from app.main import app
        from app.config import get_settings

        client = TestClient(app)
        settings = get_settings()
        headers = {"Authorization": f"Bearer {settings.internal_api_key}"}
        resp = client.post(
            "/api/internal/fmcsa-signals/detect",
            json={"feed_date": "2026-03-17"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_signals"] == 5

    def test_detect_endpoint_missing_auth_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        resp = client.post(
            "/api/internal/fmcsa-signals/detect",
            json={"feed_date": "2026-03-17"},
        )
        assert resp.status_code == 401
