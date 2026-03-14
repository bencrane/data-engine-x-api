from __future__ import annotations

import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.services import fmcsa_daily_diff_common
from app.services.fmcsa_daily_diff_common import upsert_fmcsa_daily_diff_rows


def _source_context(*, feed_name: str = "Test Feed", feed_date: str = "2026-03-12"):
    return {
        "feed_name": feed_name,
        "feed_date": feed_date,
        "download_url": "https://example.com/test",
        "source_file_variant": "daily diff",
        "source_observed_at": f"{feed_date}T12:00:00Z",
        "source_task_id": "test-task",
        "source_schedule_id": "test-schedule",
        "source_run_metadata": {"run": "test"},
    }


def _sample_rows(count: int = 2):
    return [
        {
            "row_number": i,
            "raw_fields": {"DOT_NUMBER": str(1000 + i)},
        }
        for i in range(1, count + 1)
    ]


def _simple_row_builder(row):
    return {"dot_number": row["raw_fields"]["DOT_NUMBER"]}


class _FakeCopyContext:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, data):
        pass


class _FakeCursor:
    def __init__(self):
        self._fetchall_result = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        if "information_schema.columns" in query:
            self._fetchall_result = [
                ("id",), ("dot_number",), ("feed_date",), ("source_feed_name",),
                ("row_position",), ("source_provider",), ("source_download_url",),
                ("source_file_variant",), ("source_observed_at",), ("source_task_id",),
                ("source_schedule_id",), ("source_run_metadata",), ("raw_source_row",),
                ("updated_at",), ("created_at",),
            ]

    def fetchall(self):
        return self._fetchall_result

    def copy(self, query):
        return _FakeCopyContext()


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return _FakeCursor()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


class _FakePool:
    @contextmanager
    def connection(self):
        yield _FakeConnection()

    def getconn(self):
        return _FakeConnection()

    def putconn(self, conn):
        pass


@pytest.fixture(autouse=True)
def _patch_pool(monkeypatch):
    fmcsa_daily_diff_common._get_table_columns.cache_clear()
    fake_pool = _FakePool()
    monkeypatch.setattr(
        fmcsa_daily_diff_common,
        "_get_fmcsa_connection_pool",
        lambda: fake_pool,
    )
    yield
    fmcsa_daily_diff_common._get_table_columns.cache_clear()


# --- Instrumentation tests ---


REQUIRED_PHASE_FIELDS = {
    "row_builder_ms",
    "connection_acquire_ms",
    "temp_table_create_ms",
    "copy_ms",
    "merge_ms",
    "commit_ms",
    "total_ms",
    "table_name",
    "rows_received",
    "rows_written",
}


def test_instrumentation_emits_all_phase_fields(caplog):
    with caplog.at_level(logging.INFO, logger="app.services.fmcsa_daily_diff_common"):
        upsert_fmcsa_daily_diff_rows(
            table_name="motor_carrier_census_records",
            source_context=_source_context(),
            rows=_sample_rows(2),
            row_builder=_simple_row_builder,
        )

    phase_records = [r for r in caplog.records if r.getMessage() == "fmcsa_batch_persist_phases"]
    assert len(phase_records) == 1
    record = phase_records[0]

    for field in REQUIRED_PHASE_FIELDS:
        assert hasattr(record, field), f"Missing phase field: {field}"

    assert record.table_name == "motor_carrier_census_records"
    assert record.rows_received == 2
    assert record.rows_written == 2
    assert record.error is False
    assert record.total_ms >= 0


def test_instrumentation_logs_on_failure_with_error_flag(caplog):
    class _FailingCursor(_FakeCursor):
        def execute(self, query, params=None):
            if "information_schema.columns" in query:
                return super().execute(query, params)
            if "INSERT INTO" in query:
                raise RuntimeError("merge exploded")

    class _FailingConnection(_FakeConnection):
        def cursor(self):
            return _FailingCursor()

    class _FailingPool(_FakePool):
        @contextmanager
        def connection(self):
            yield _FailingConnection()

    with patch.object(
        fmcsa_daily_diff_common,
        "_get_fmcsa_connection_pool",
        return_value=_FailingPool(),
    ):
        fmcsa_daily_diff_common._get_table_columns.cache_clear()
        with caplog.at_level(logging.INFO, logger="app.services.fmcsa_daily_diff_common"):
            with pytest.raises(RuntimeError, match="merge exploded"):
                upsert_fmcsa_daily_diff_rows(
                    table_name="motor_carrier_census_records",
                    source_context=_source_context(),
                    rows=_sample_rows(1),
                    row_builder=_simple_row_builder,
                )

    phase_records = [r for r in caplog.records if r.getMessage() == "fmcsa_batch_persist_phases"]
    assert len(phase_records) == 1
    record = phase_records[0]

    assert record.error is True
    assert record.table_name == "motor_carrier_census_records"
    assert record.total_ms >= 0
    # Phases before the failure should still be recorded
    assert hasattr(record, "row_builder_ms")
    assert hasattr(record, "connection_acquire_ms")
    assert hasattr(record, "temp_table_create_ms")
    assert hasattr(record, "copy_ms")


def test_instrumentation_logs_on_empty_rows(caplog):
    with caplog.at_level(logging.INFO, logger="app.services.fmcsa_daily_diff_common"):
        result = upsert_fmcsa_daily_diff_rows(
            table_name="motor_carrier_census_records",
            source_context=_source_context(),
            rows=[],
            row_builder=_simple_row_builder,
        )

    assert result["rows_written"] == 0
    phase_records = [r for r in caplog.records if r.getMessage() == "fmcsa_batch_persist_phases"]
    assert len(phase_records) == 1
    assert phase_records[0].rows_written == 0
    assert phase_records[0].total_ms >= 0


# --- Connection pooling tests ---


def test_pool_singleton_returns_same_pool():
    """Two calls to _get_fmcsa_connection_pool return the same object."""
    saved_pool = fmcsa_daily_diff_common._fmcsa_pool
    try:
        # Reimport to get the real function
        import importlib
        importlib.reload(fmcsa_daily_diff_common)

        fmcsa_daily_diff_common._fmcsa_pool = None
        mock_pool_instance = MagicMock()
        with patch("app.services.fmcsa_daily_diff_common.ConnectionPool", return_value=mock_pool_instance) as mock_pool_cls:
            with patch.object(
                fmcsa_daily_diff_common,
                "get_settings",
                return_value=MagicMock(database_url="postgresql://fake:5432/test"),
            ):
                pool1 = fmcsa_daily_diff_common._get_fmcsa_connection_pool()
                pool2 = fmcsa_daily_diff_common._get_fmcsa_connection_pool()

                assert pool1 is pool2
                assert mock_pool_cls.call_count == 1
                mock_pool_cls.assert_called_once_with(
                    conninfo="postgresql://fake:5432/test",
                    min_size=1,
                    max_size=4,
                    timeout=30.0,
                )
    finally:
        fmcsa_daily_diff_common._fmcsa_pool = saved_pool
        importlib.reload(fmcsa_daily_diff_common)


def test_pool_import_failure_raises_clear_error():
    """If psycopg_pool is unavailable, importing the module fails clearly.

    We choose fail-fast over fallback because silently falling back to
    per-call connect() would mask the performance regression that connection
    pooling is meant to fix. A clear import error at startup is better than
    a silent degradation discovered only in production latency metrics.
    """
    import importlib
    import sys

    saved = sys.modules.get("psycopg_pool")
    sys.modules["psycopg_pool"] = None  # type: ignore[assignment]
    try:
        with pytest.raises((ImportError, TypeError)):
            importlib.reload(fmcsa_daily_diff_common)
    finally:
        if saved is not None:
            sys.modules["psycopg_pool"] = saved
        else:
            sys.modules.pop("psycopg_pool", None)
        importlib.reload(fmcsa_daily_diff_common)
