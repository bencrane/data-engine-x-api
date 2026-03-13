"""Tests for FMCSA artifact ingest endpoint and service."""
from __future__ import annotations

import gzip
import hashlib
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.fmcsa_artifact_ingest import (
    FMCSA_FEED_REGISTRY,
    ChecksumMismatchError,
    DEFAULT_CHUNK_SIZE,
    ingest_artifact,
    parse_ndjson_rows,
    verify_checksum,
)


# --- Helpers ---


def _make_rows(count: int) -> list[dict[str, Any]]:
    return [
        {
            "row_number": i + 1,
            "raw_values": [f"val{i}_0", f"val{i}_1"],
            "raw_fields": {"col0": f"val{i}_0", "col1": f"val{i}_1"},
        }
        for i in range(count)
    ]


def _make_ndjson_gz(rows: list[dict[str, Any]]) -> tuple[bytes, str]:
    ndjson = "\n".join(json.dumps(row) for row in rows) + "\n"
    gz = gzip.compress(ndjson.encode("utf-8"))
    checksum = hashlib.sha256(gz).hexdigest()
    return gz, checksum


def _make_manifest(
    rows: list[dict[str, Any]] | None = None,
    feed_name: str = "AuthHist",
    feed_date: str = "2026-03-10",
    checksum: str | None = None,
) -> dict[str, Any]:
    if rows is None:
        rows = _make_rows(3)
    gz, actual_checksum = _make_ndjson_gz(rows)
    return {
        "feed_name": feed_name,
        "feed_date": feed_date,
        "download_url": "https://example.com/feed.csv",
        "source_file_variant": "daily diff",
        "source_observed_at": "2026-03-10T12:00:00Z",
        "source_task_id": "test-task",
        "source_schedule_id": None,
        "source_run_metadata": {"test": True},
        "artifact_bucket": "fmcsa-artifacts",
        "artifact_path": "AuthHist/2026-03-10/test.ndjson.gz",
        "row_count": len(rows),
        "artifact_checksum": checksum or actual_checksum,
    }


def _mock_upsert_func(rows_written: int | None = None, side_effect: Exception | None = None):
    """Create a mock upsert function that matches the service upsert signature."""
    def _upsert(*, source_context: Any, rows: Any) -> dict[str, Any]:
        if side_effect is not None:
            raise side_effect
        return {"rows_written": rows_written if rows_written is not None else len(rows)}
    return _upsert


def _patch_registry(feed_name: str, mock_func):
    """Temporarily replace a registry entry's upsert function."""
    original = FMCSA_FEED_REGISTRY[feed_name]
    table_name = original[0]
    FMCSA_FEED_REGISTRY[feed_name] = (table_name, mock_func)

    class _Restore:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            FMCSA_FEED_REGISTRY[feed_name] = original

    return _Restore()


# --- Unit tests ---


class TestVerifyChecksum:
    def test_matching_checksum(self) -> None:
        data = b"test data"
        checksum = hashlib.sha256(data).hexdigest()
        assert verify_checksum(data, checksum) is True

    def test_mismatched_checksum(self) -> None:
        assert verify_checksum(b"test data", "0" * 64) is False


class TestParseNdjsonRows:
    def test_parses_valid_ndjson(self) -> None:
        rows = _make_rows(3)
        ndjson = "\n".join(json.dumps(r) for r in rows) + "\n"
        parsed = parse_ndjson_rows(ndjson.encode("utf-8"))
        assert len(parsed) == 3
        assert parsed[0]["row_number"] == 1
        assert parsed[2]["row_number"] == 3

    def test_skips_blank_lines(self) -> None:
        ndjson = json.dumps({"row_number": 1, "raw_values": [], "raw_fields": {}}) + "\n\n\n"
        parsed = parse_ndjson_rows(ndjson.encode("utf-8"))
        assert len(parsed) == 1


class TestFeedRegistry:
    def test_registry_covers_all_31_active_feed_names(self) -> None:
        expected_feeds = {
            "AuthHist", "Revocation", "Insurance", "ActPendInsur", "InsHist",
            "Carrier", "Rejected", "BOC3",
            "InsHist - All With History", "BOC3 - All With History",
            "ActPendInsur - All With History", "Rejected - All With History",
            "AuthHist - All With History", "Carrier - All With History",
            "Revocation - All With History", "Insur - All With History",
            "Crash File", "Inspections Per Unit", "Special Studies",
            "OUT OF SERVICE ORDERS", "Inspections and Citations",
            "Vehicle Inspections and Violations", "Company Census File",
            "Vehicle Inspection File",
            "SMS AB PassProperty", "SMS C PassProperty",
            "SMS Input - Violation", "SMS Input - Inspection",
            "SMS Input - Motor Carrier Census",
            "SMS AB Pass", "SMS C Pass",
        }
        assert set(FMCSA_FEED_REGISTRY.keys()) == expected_feeds

    def test_every_entry_has_table_name_and_callable(self) -> None:
        for feed_name, (table_name, upsert_func) in FMCSA_FEED_REGISTRY.items():
            assert isinstance(table_name, str), f"{feed_name}: table_name is not a string"
            assert len(table_name) > 0, f"{feed_name}: table_name is empty"
            assert callable(upsert_func), f"{feed_name}: upsert_func is not callable"


class TestIngestArtifact:
    """Test the ingest_artifact function with mocked dependencies."""

    def _patch_download(self, rows: list[dict[str, Any]]):
        gz, checksum = _make_ndjson_gz(rows)
        return patch(
            "app.services.fmcsa_artifact_ingest.download_artifact_from_storage",
            return_value=gz,
        ), checksum

    def test_successful_ingest_small_batch(self) -> None:
        rows = _make_rows(5)
        download_patch, checksum = self._patch_download(rows)
        call_log: list[int] = []

        def _mock(*, source_context: Any, rows: Any) -> dict[str, Any]:
            call_log.append(len(rows))
            return {"rows_written": len(rows)}

        with download_patch, _patch_registry("AuthHist", _mock):
            result = ingest_artifact(
                feed_name="AuthHist",
                feed_date="2026-03-10",
                download_url="https://example.com/feed.csv",
                source_file_variant="daily diff",
                source_observed_at="2026-03-10T12:00:00Z",
                source_task_id="test-task",
                source_schedule_id=None,
                source_run_metadata={},
                artifact_bucket="fmcsa-artifacts",
                artifact_path="AuthHist/2026-03-10/test.ndjson.gz",
                row_count=5,
                artifact_checksum=checksum,
            )

        assert result["feed_name"] == "AuthHist"
        assert result["table_name"] == "operating_authority_histories"
        assert result["rows_received"] == 5
        assert result["rows_written"] == 5
        assert result["checksum_verified"] is True
        assert len(call_log) == 1  # single chunk
        assert call_log[0] == 5

    def test_chunked_processing(self) -> None:
        rows = _make_rows(25)
        download_patch, checksum = self._patch_download(rows)
        call_log: list[int] = []

        def _mock(*, source_context: Any, rows: Any) -> dict[str, Any]:
            call_log.append(len(rows))
            return {"rows_written": len(rows)}

        with download_patch, _patch_registry("AuthHist", _mock):
            result = ingest_artifact(
                feed_name="AuthHist",
                feed_date="2026-03-10",
                download_url="https://example.com/feed.csv",
                source_file_variant="daily diff",
                source_observed_at="2026-03-10T12:00:00Z",
                source_task_id="test-task",
                source_schedule_id=None,
                source_run_metadata={},
                artifact_bucket="fmcsa-artifacts",
                artifact_path="AuthHist/2026-03-10/test.ndjson.gz",
                row_count=25,
                artifact_checksum=checksum,
                chunk_size=10,
            )

        # 25 rows / 10 per chunk = 3 chunks (10, 10, 5)
        assert len(call_log) == 3
        assert call_log == [10, 10, 5]
        assert result["rows_written"] == 25
        assert result["rows_received"] == 25

    def test_checksum_mismatch_raises(self) -> None:
        rows = _make_rows(3)
        download_patch, _ = self._patch_download(rows)

        with download_patch, pytest.raises(ChecksumMismatchError, match="checksum mismatch"):
            ingest_artifact(
                feed_name="AuthHist",
                feed_date="2026-03-10",
                download_url="https://example.com/feed.csv",
                source_file_variant="daily diff",
                source_observed_at="2026-03-10T12:00:00Z",
                source_task_id="test-task",
                source_schedule_id=None,
                source_run_metadata={},
                artifact_bucket="fmcsa-artifacts",
                artifact_path="AuthHist/2026-03-10/test.ndjson.gz",
                row_count=3,
                artifact_checksum="bad_checksum_" + "0" * 52,
            )

    def test_unknown_feed_raises_valueerror(self) -> None:
        rows = _make_rows(1)
        download_patch, checksum = self._patch_download(rows)

        with download_patch, pytest.raises(ValueError, match="Unknown FMCSA feed_name"):
            ingest_artifact(
                feed_name="NonexistentFeed",
                feed_date="2026-03-10",
                download_url="https://example.com",
                source_file_variant="daily diff",
                source_observed_at="2026-03-10T12:00:00Z",
                source_task_id="test-task",
                source_schedule_id=None,
                source_run_metadata={},
                artifact_bucket="fmcsa-artifacts",
                artifact_path="test.ndjson.gz",
                row_count=1,
                artifact_checksum=checksum,
            )

    def test_streaming_chunked_processing_large_batch(self) -> None:
        """Verify streaming decompression processes 105 rows in 11 chunks (10+10+...+5)."""
        rows = _make_rows(105)
        download_patch, checksum = self._patch_download(rows)
        call_log: list[int] = []

        def _mock(*, source_context: Any, rows: Any) -> dict[str, Any]:
            call_log.append(len(rows))
            return {"rows_written": len(rows)}

        with download_patch, _patch_registry("AuthHist", _mock):
            result = ingest_artifact(
                feed_name="AuthHist",
                feed_date="2026-03-10",
                download_url="https://example.com/feed.csv",
                source_file_variant="daily diff",
                source_observed_at="2026-03-10T12:00:00Z",
                source_task_id="test-task",
                source_schedule_id=None,
                source_run_metadata={},
                artifact_bucket="fmcsa-artifacts",
                artifact_path="AuthHist/2026-03-10/test.ndjson.gz",
                row_count=105,
                artifact_checksum=checksum,
                chunk_size=10,
            )

        # 105 rows / 10 per chunk = 11 chunks (10×10 + 1×5)
        assert len(call_log) == 11
        assert call_log == [10] * 10 + [5]
        assert result["rows_received"] == 105
        assert result["rows_written"] == 105

    def test_chunk_failure_stops_processing(self) -> None:
        rows = _make_rows(25)
        download_patch, checksum = self._patch_download(rows)
        call_count = 0

        def _failing(*, source_context: Any, rows: Any) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("DB connection lost")
            return {"rows_written": len(rows)}

        with download_patch, _patch_registry("AuthHist", _failing):
            with pytest.raises(RuntimeError, match="chunk 2"):
                ingest_artifact(
                    feed_name="AuthHist",
                    feed_date="2026-03-10",
                    download_url="https://example.com/feed.csv",
                    source_file_variant="daily diff",
                    source_observed_at="2026-03-10T12:00:00Z",
                    source_task_id="test-task",
                    source_schedule_id=None,
                    source_run_metadata={},
                    artifact_bucket="fmcsa-artifacts",
                    artifact_path="AuthHist/2026-03-10/test.ndjson.gz",
                    row_count=25,
                    artifact_checksum=checksum,
                    chunk_size=10,
                )

        assert call_count == 2


class TestIngestArtifactEndpoint:
    """Test the /api/internal/fmcsa/ingest-artifact endpoint via TestClient."""

    @pytest.fixture
    def app_client(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
        monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
        monkeypatch.setenv("TRIGGER_SECRET_KEY", "test-trigger")
        monkeypatch.setenv("TRIGGER_PROJECT_ID", "test-proj")
        monkeypatch.setenv("JWT_SECRET", "test-jwt")
        monkeypatch.setenv("SUPER_ADMIN_JWT_SECRET", "test-sa-jwt")
        monkeypatch.setenv("INTERNAL_API_KEY", "test-key")

        from app.config import get_settings
        get_settings.cache_clear()

        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_checksum_mismatch_returns_422(self, app_client) -> None:
        rows = _make_rows(3)
        manifest = _make_manifest(rows, checksum="0" * 64)

        with patch(
            "app.services.fmcsa_artifact_ingest.download_artifact_from_storage",
            return_value=_make_ndjson_gz(rows)[0],
        ):
            response = app_client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=manifest,
                headers={"Authorization": "Bearer test-key"},
            )

        assert response.status_code == 422
        body = response.json()
        error_text = (body.get("detail") or body.get("error") or "").lower()
        assert "checksum mismatch" in error_text

    def test_successful_ingest_returns_confirmation(self, app_client) -> None:
        rows = _make_rows(3)
        gz, checksum = _make_ndjson_gz(rows)
        manifest = _make_manifest(rows)

        def _mock(*, source_context: Any, rows: Any) -> dict[str, Any]:
            return {"rows_written": len(rows)}

        with patch(
            "app.services.fmcsa_artifact_ingest.download_artifact_from_storage",
            return_value=gz,
        ), _patch_registry("AuthHist", _mock):
            response = app_client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=manifest,
                headers={"Authorization": "Bearer test-key"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["feed_name"] == "AuthHist"
        assert data["table_name"] == "operating_authority_histories"
        assert data["rows_received"] == 3
        assert data["rows_written"] == 3
        assert data["checksum_verified"] is True

    def test_persistence_failure_returns_500(self, app_client) -> None:
        rows = _make_rows(3)
        gz, checksum = _make_ndjson_gz(rows)
        manifest = _make_manifest(rows)

        def _failing(*, source_context: Any, rows: Any) -> dict[str, Any]:
            raise RuntimeError("DB dead")

        with patch(
            "app.services.fmcsa_artifact_ingest.download_artifact_from_storage",
            return_value=gz,
        ), _patch_registry("AuthHist", _failing):
            response = app_client.post(
                "/api/internal/fmcsa/ingest-artifact",
                json=manifest,
                headers={"Authorization": "Bearer test-key"},
            )

        assert response.status_code == 500
        body = response.json()
        error_text = (body.get("detail") or body.get("error") or "").lower()
        assert "chunk 1" in error_text
