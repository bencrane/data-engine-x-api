# tests/test_fmcsa_ingest_service.py — Tests for the standalone FMCSA ingest service

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Mock get_settings before importing the app so auth uses our test key
_mock_settings = MagicMock()
_mock_settings.internal_api_key = "test-internal-key"

with patch("app.routers.fmcsa_ingest.get_settings", return_value=_mock_settings):
    from app.fmcsa_ingest_main import app

from app.middleware.gzip_request import GzipRequestMiddleware
from app.routers.fmcsa_ingest import (
    InternalFmcsaArtifactIngestRequest,
    InternalFmcsaDailyDiffRow,
    InternalUpsertFmcsaDailyDiffBatchRequest,
    _build_fmcsa_source_context,
)

TEST_API_KEY = "test-internal-key"
AUTH_HEADER = {"Authorization": f"Bearer {TEST_API_KEY}"}

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_settings():
    """Ensure get_settings returns our test key for every test."""
    with patch("app.routers.fmcsa_ingest.get_settings", return_value=_mock_settings):
        yield


def _make_batch_payload(records=None):
    return {
        "feed_name": "test_feed",
        "feed_date": "2026-03-17",
        "download_url": "https://example.com/feed.zip",
        "source_file_variant": "daily diff",
        "source_observed_at": "2026-03-17T00:00:00Z",
        "source_task_id": "task-123",
        "source_schedule_id": "sched-456",
        "source_run_metadata": {"run_id": "run-789"},
        "records": records or [{"row_number": 1, "raw_fields": {"col1": "val1"}}],
        "use_snapshot_replace": False,
        "is_first_chunk": False,
    }


def _make_artifact_payload():
    return {
        "feed_name": "test_feed",
        "feed_date": "2026-03-17",
        "download_url": "https://example.com/feed.zip",
        "source_file_variant": "daily diff",
        "source_observed_at": "2026-03-17T00:00:00Z",
        "source_task_id": "task-123",
        "source_schedule_id": "sched-456",
        "source_run_metadata": {"run_id": "run-789"},
        "artifact_bucket": "fmcsa-artifacts",
        "artifact_path": "test/feed.ndjson.gz",
        "row_count": 100,
        "artifact_checksum": "abc123",
    }


# ---------------------------------------------------------------------------
# 1. Health check
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "fmcsa-ingest"


# ---------------------------------------------------------------------------
# 2. App entrypoint
# ---------------------------------------------------------------------------

class TestAppEntrypoint:
    def test_gzip_middleware_registered(self):
        middleware_classes = [m.cls for m in app.user_middleware]
        assert GzipRequestMiddleware in middleware_classes

    def test_router_mounted_at_api_internal(self):
        paths = [route.path for route in app.routes]
        assert "/api/internal/carrier-registrations/upsert-batch" in paths

    def test_all_fmcsa_paths_registered(self):
        paths = set(route.path for route in app.routes)
        expected_paths = [
            "/api/internal/operating-authority-histories/upsert-batch",
            "/api/internal/operating-authority-revocations/upsert-batch",
            "/api/internal/insurance-policies/upsert-batch",
            "/api/internal/insurance-policy-filings/upsert-batch",
            "/api/internal/insurance-policy-history-events/upsert-batch",
            "/api/internal/carrier-registrations/upsert-batch",
            "/api/internal/carrier-safety-basic-measures/upsert-batch",
            "/api/internal/commercial-vehicle-crashes/upsert-batch",
            "/api/internal/carrier-safety-basic-percentiles/upsert-batch",
            "/api/internal/vehicle-inspection-units/upsert-batch",
            "/api/internal/carrier-inspection-violations/upsert-batch",
            "/api/internal/vehicle-inspection-special-studies/upsert-batch",
            "/api/internal/vehicle-inspection-citations/upsert-batch",
            "/api/internal/motor-carrier-census-records/upsert-batch",
            "/api/internal/out-of-service-orders/upsert-batch",
            "/api/internal/process-agent-filings/upsert-batch",
            "/api/internal/insurance-filing-rejections/upsert-batch",
            "/api/internal/carrier-inspections/upsert-batch",
            "/api/internal/fmcsa/ingest-artifact",
        ]
        for path in expected_paths:
            assert path in paths, f"Missing endpoint: {path}"


# ---------------------------------------------------------------------------
# 3. Auth tests
# ---------------------------------------------------------------------------

class TestAuth:
    def test_missing_auth_returns_401(self):
        response = client.post(
            "/api/internal/carrier-registrations/upsert-batch",
            json=_make_batch_payload(),
        )
        assert response.status_code == 401

    def test_wrong_auth_returns_401(self):
        response = client.post(
            "/api/internal/carrier-registrations/upsert-batch",
            json=_make_batch_payload(),
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert response.status_code == 401

    def test_artifact_missing_auth_returns_401(self):
        response = client.post(
            "/api/internal/fmcsa/ingest-artifact",
            json=_make_artifact_payload(),
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# 4. Source context helper
# ---------------------------------------------------------------------------

class TestBuildFmcsaSourceContext:
    def test_maps_all_fields(self):
        payload = InternalUpsertFmcsaDailyDiffBatchRequest(
            feed_name="test",
            feed_date="2026-03-17",
            download_url="https://example.com",
            source_file_variant="daily diff",
            source_observed_at="2026-03-17T00:00:00Z",
            source_task_id="task-1",
            source_schedule_id="sched-1",
            source_run_metadata={"key": "val"},
            records=[],
            use_snapshot_replace=True,
            is_first_chunk=True,
        )
        ctx = _build_fmcsa_source_context(payload)
        assert ctx["feed_name"] == "test"
        assert ctx["feed_date"] == "2026-03-17"
        assert ctx["download_url"] == "https://example.com"
        assert ctx["source_file_variant"] == "daily diff"
        assert ctx["source_observed_at"] == "2026-03-17T00:00:00Z"
        assert ctx["source_task_id"] == "task-1"
        assert ctx["source_schedule_id"] == "sched-1"
        assert ctx["source_run_metadata"] == {"key": "val"}
        assert ctx["use_snapshot_replace"] is True
        assert ctx["is_first_chunk"] is True

    def test_optional_fields_default_to_none(self):
        payload = InternalUpsertFmcsaDailyDiffBatchRequest(
            feed_name="test",
            feed_date="2026-03-17",
            download_url="https://example.com",
            source_file_variant="daily",
            source_observed_at="2026-03-17T00:00:00Z",
            source_task_id="task-1",
            source_run_metadata={},
            records=[],
        )
        ctx = _build_fmcsa_source_context(payload)
        assert ctx["source_schedule_id"] is None
        assert ctx["use_snapshot_replace"] is False
        assert ctx["is_first_chunk"] is False


# ---------------------------------------------------------------------------
# 5. Upsert-batch endpoint tests (all 18 tables)
# ---------------------------------------------------------------------------

_R = "app.routers.fmcsa_ingest"

UPSERT_ENDPOINTS = [
    ("/api/internal/operating-authority-histories/upsert-batch", f"{_R}.upsert_operating_authority_histories"),
    ("/api/internal/operating-authority-revocations/upsert-batch", f"{_R}.upsert_operating_authority_revocations"),
    ("/api/internal/insurance-policies/upsert-batch", f"{_R}.upsert_insurance_policies"),
    ("/api/internal/insurance-policy-filings/upsert-batch", f"{_R}.upsert_insurance_policy_filings"),
    ("/api/internal/insurance-policy-history-events/upsert-batch", f"{_R}.upsert_insurance_policy_history_events"),
    ("/api/internal/carrier-registrations/upsert-batch", f"{_R}.upsert_carrier_registrations"),
    ("/api/internal/carrier-safety-basic-measures/upsert-batch", f"{_R}.upsert_carrier_safety_basic_measures"),
    ("/api/internal/commercial-vehicle-crashes/upsert-batch", f"{_R}.upsert_commercial_vehicle_crashes"),
    ("/api/internal/carrier-safety-basic-percentiles/upsert-batch", f"{_R}.upsert_carrier_safety_basic_percentiles"),
    ("/api/internal/vehicle-inspection-units/upsert-batch", f"{_R}.upsert_vehicle_inspection_units"),
    ("/api/internal/carrier-inspection-violations/upsert-batch", f"{_R}.upsert_carrier_inspection_violations"),
    ("/api/internal/vehicle-inspection-special-studies/upsert-batch", f"{_R}.upsert_vehicle_inspection_special_studies"),
    ("/api/internal/carrier-inspections/upsert-batch", f"{_R}.upsert_carrier_inspections"),
    ("/api/internal/vehicle-inspection-citations/upsert-batch", f"{_R}.upsert_vehicle_inspection_citations"),
    ("/api/internal/motor-carrier-census-records/upsert-batch", f"{_R}.upsert_motor_carrier_census_records"),
    ("/api/internal/out-of-service-orders/upsert-batch", f"{_R}.upsert_out_of_service_orders"),
    ("/api/internal/process-agent-filings/upsert-batch", f"{_R}.upsert_process_agent_filings"),
    ("/api/internal/insurance-filing-rejections/upsert-batch", f"{_R}.upsert_insurance_filing_rejections"),
]


class TestUpsertBatchEndpoints:
    @pytest.mark.parametrize("path,mock_target", UPSERT_ENDPOINTS)
    def test_upsert_returns_data_envelope(self, path, mock_target):
        mock_result = {"upserted": 1, "skipped": 0}
        with patch(mock_target, return_value=mock_result):
            response = client.post(path, json=_make_batch_payload(), headers=AUTH_HEADER)
        assert response.status_code == 200
        assert response.json() == {"data": mock_result}

    @pytest.mark.parametrize("path,mock_target", UPSERT_ENDPOINTS)
    def test_upsert_passes_source_context_and_rows(self, path, mock_target):
        with patch(mock_target) as mock_fn:
            mock_fn.return_value = {"upserted": 0}
            client.post(path, json=_make_batch_payload(), headers=AUTH_HEADER)
            mock_fn.assert_called_once()
            kwargs = mock_fn.call_args.kwargs
            assert kwargs["source_context"]["feed_name"] == "test_feed"
            assert len(kwargs["rows"]) == 1
            assert kwargs["rows"][0]["row_number"] == 1


# ---------------------------------------------------------------------------
# 6. Artifact ingest endpoint
# ---------------------------------------------------------------------------

class TestArtifactIngestEndpoint:
    def test_artifact_ingest_returns_data_envelope(self):
        mock_result = {"rows_ingested": 100}
        with patch(
            "app.services.fmcsa_artifact_ingest.ingest_artifact",
            return_value=mock_result,
        ):
            response = client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=_make_artifact_payload(),
                headers=AUTH_HEADER,
            )
        assert response.status_code == 200
        assert response.json() == {"data": mock_result}

    def test_artifact_checksum_mismatch_returns_422(self):
        from app.services.fmcsa_artifact_ingest import ChecksumMismatchError

        with patch(
            "app.services.fmcsa_artifact_ingest.ingest_artifact",
            side_effect=ChecksumMismatchError("checksum mismatch"),
        ):
            response = client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=_make_artifact_payload(),
                headers=AUTH_HEADER,
            )
        assert response.status_code == 422

    def test_artifact_value_error_returns_422(self):
        with patch(
            "app.services.fmcsa_artifact_ingest.ingest_artifact",
            side_effect=ValueError("bad value"),
        ):
            response = client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=_make_artifact_payload(),
                headers=AUTH_HEADER,
            )
        assert response.status_code == 422

    def test_artifact_runtime_error_returns_500(self):
        with patch(
            "app.services.fmcsa_artifact_ingest.ingest_artifact",
            side_effect=RuntimeError("something broke"),
        ):
            response = client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=_make_artifact_payload(),
                headers=AUTH_HEADER,
            )
        assert response.status_code == 500


# ---------------------------------------------------------------------------
# 7. Endpoint path compatibility (all 19 paths Trigger.dev calls)
# ---------------------------------------------------------------------------

class TestEndpointPathCompatibility:
    REQUIRED_PATHS = [
        "/api/internal/operating-authority-histories/upsert-batch",
        "/api/internal/operating-authority-revocations/upsert-batch",
        "/api/internal/insurance-policies/upsert-batch",
        "/api/internal/insurance-policy-filings/upsert-batch",
        "/api/internal/insurance-policy-history-events/upsert-batch",
        "/api/internal/carrier-registrations/upsert-batch",
        "/api/internal/carrier-safety-basic-measures/upsert-batch",
        "/api/internal/commercial-vehicle-crashes/upsert-batch",
        "/api/internal/carrier-safety-basic-percentiles/upsert-batch",
        "/api/internal/vehicle-inspection-units/upsert-batch",
        "/api/internal/carrier-inspection-violations/upsert-batch",
        "/api/internal/vehicle-inspection-special-studies/upsert-batch",
        "/api/internal/vehicle-inspection-citations/upsert-batch",
        "/api/internal/motor-carrier-census-records/upsert-batch",
        "/api/internal/out-of-service-orders/upsert-batch",
        "/api/internal/process-agent-filings/upsert-batch",
        "/api/internal/insurance-filing-rejections/upsert-batch",
        "/api/internal/carrier-inspections/upsert-batch",
        "/api/internal/fmcsa/ingest-artifact",
    ]

    def test_all_trigger_paths_are_registered(self):
        registered = set(route.path for route in app.routes)
        for path in self.REQUIRED_PATHS:
            assert path in registered, f"Missing endpoint path: {path}"

    def test_exact_count_of_fmcsa_endpoints(self):
        fmcsa_routes = [
            route for route in app.routes
            if hasattr(route, "path") and route.path.startswith("/api/internal/")
        ]
        assert len(fmcsa_routes) == 19
