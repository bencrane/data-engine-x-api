from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.routers import internal
from app.services import fmcsa_daily_diff_common
from app.services.insurance_policies import upsert_insurance_policies
from app.services.insurance_policy_filings import upsert_insurance_policy_filings
from app.services.insurance_policy_history_events import upsert_insurance_policy_history_events
from app.services.operating_authority_histories import upsert_operating_authority_histories
from app.services.operating_authority_revocations import upsert_operating_authority_revocations


@dataclass
class _Result:
    data: list[dict]


class _FakeTableQuery:
    def __init__(self, client: "_FakeSupabaseClient", table_name: str):
        self.client = client
        self.table_name = table_name
        self.mode: str | None = None
        self.select_columns: str | None = None
        self.filter_values: list[str] = []
        self.upsert_rows: list[dict] = []

    def select(self, columns: str):
        self.mode = "select"
        self.select_columns = columns
        return self

    def in_(self, column: str, values: list[str]):
        assert column == "record_fingerprint"
        self.filter_values = values
        return self

    def upsert(self, rows: list[dict], on_conflict: str):
        assert on_conflict == "record_fingerprint"
        self.mode = "upsert"
        self.upsert_rows = rows
        return self

    def execute(self):
        table = self.client.tables.setdefault(self.table_name, {})

        if self.mode == "select":
            selected_rows = []
            for fingerprint in self.filter_values:
                existing = table.get(fingerprint)
                if existing is not None:
                    selected_rows.append(
                        {
                            "record_fingerprint": existing["record_fingerprint"],
                            "first_observed_at": existing["first_observed_at"],
                        }
                    )
            return _Result(data=selected_rows)

        if self.mode == "upsert":
            persisted_rows = []
            for row in self.upsert_rows:
                fingerprint = row["record_fingerprint"]
                existing = table.get(fingerprint)
                if existing is None:
                    stored = {
                        "id": f"{self.table_name}-{len(table) + 1}",
                        "created_at": row["updated_at"],
                        **row,
                    }
                else:
                    stored = {
                        **existing,
                        **row,
                        "created_at": existing["created_at"],
                    }
                table[fingerprint] = stored
                persisted_rows.append(stored)
            return _Result(data=persisted_rows)

        raise AssertionError(f"Unsupported mode for fake table query: {self.mode}")


class _FakeSupabaseClient:
    def __init__(self):
        self.tables: dict[str, dict[str, dict]] = {}

    def table(self, table_name: str):
        return _FakeTableQuery(self, table_name)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeSupabaseClient:
    client = _FakeSupabaseClient()
    monkeypatch.setattr(fmcsa_daily_diff_common, "get_supabase_client", lambda: client)
    return client


def _source_context(*, feed_name: str, observed_at: str) -> dict:
    return {
        "feed_name": feed_name,
        "download_url": f"https://example.com/{feed_name.lower()}",
        "source_file_variant": "daily diff",
        "source_observed_at": observed_at,
        "source_task_id": f"{feed_name.lower()}-task",
        "source_schedule_id": f"{feed_name.lower()}-schedule",
        "source_run_metadata": {"run": feed_name},
    }


def test_upsert_operating_authority_histories_persists_typed_row(fake_client: _FakeSupabaseClient):
    result = upsert_operating_authority_histories(
        source_context=_source_context(feed_name="AuthHist", observed_at="2026-03-10T15:00:00Z"),
        rows=[
            {
                "row_number": 1,
                "raw_values": [
                    "MC123456",
                    "12345678",
                    "0001",
                    "Common",
                    "Granted",
                    "03/10/2024",
                    "Revoked",
                    "03/09/2026",
                    "03/10/2026",
                ],
                "raw_fields": {
                    "Docket Number": "MC123456",
                    "USDOT Number": "12345678",
                    "Sub Number": "0001",
                    "Operating Authority Type": "Common",
                    "Original Authority Action Description": "Granted",
                    "Original Authority Action Served Date": "03/10/2024",
                    "Final Authority Action Description": "Revoked",
                    "Final Authority Decision Date": "03/09/2026",
                    "Final Authority Served Date": "03/10/2026",
                },
            }
        ],
    )

    assert result["rows_received"] == 1
    stored = next(iter(fake_client.tables["operating_authority_histories"].values()))
    assert stored["docket_number"] == "MC123456"
    assert stored["original_authority_action_served_date"] == "2024-03-10"
    assert stored["final_authority_served_date"] == "2026-03-10"


def test_upsert_operating_authority_revocations_preserves_first_observed_on_rerun(
    fake_client: _FakeSupabaseClient,
):
    row = {
        "row_number": 1,
        "raw_values": [
            "MC999999",
            "87654321",
            "Broker",
            "03/08/2026",
            "Insurance",
            "03/10/2026",
        ],
        "raw_fields": {
            "Docket Number": "MC999999",
            "USDOT Number": "87654321",
            "Operating Authority Registration Type": "Broker",
            "Serve Date": "03/08/2026",
            "Revocation Type": "Insurance",
            "Effective Date": "03/10/2026",
        },
    }

    first_result = upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-10T15:05:00Z"),
        rows=[row],
    )
    second_result = upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-11T15:05:00Z"),
        rows=[row],
    )

    assert first_result["inserted_count"] == 1
    assert second_result["updated_count"] == 1

    stored = next(iter(fake_client.tables["operating_authority_revocations"].values()))
    assert stored["first_observed_at"] == "2026-03-10T15:05:00Z"
    assert stored["last_observed_at"] == "2026-03-11T15:05:00Z"


def test_upsert_insurance_policies_preserves_blank_row_removal_signal(
    fake_client: _FakeSupabaseClient,
):
    result = upsert_insurance_policies(
        source_context=_source_context(feed_name="Insurance", observed_at="2026-03-10T15:10:00Z"),
        rows=[
            {
                "row_number": 7,
                "raw_values": ["MC111111", "", "", "00000", "00000", "", "", "", ""],
                "raw_fields": {
                    "Docket Number": "MC111111",
                    "Insurance Type": "",
                    "BI&PD Class": "",
                    "BI&PD Maximum Dollar Limit": "00000",
                    "BI&PD Underlying Dollar Limit": "00000",
                    "Policy Number": "",
                    "Effective Date": "",
                    "Form Code": "",
                    "Insurance Company Name": "",
                },
            }
        ],
    )

    assert result["rows_received"] == 1
    stored = next(iter(fake_client.tables["insurance_policies"].values()))
    assert stored["docket_number"] == "MC111111"
    assert stored["is_removal_signal"] is True
    assert stored["removal_signal_reason"] == "daily_diff_blank_or_zero_row"
    assert stored["policy_number"] is None


def test_upsert_insurance_policy_filings_persists_typed_row(fake_client: _FakeSupabaseClient):
    result = upsert_insurance_policy_filings(
        source_context=_source_context(feed_name="ActPendInsur", observed_at="2026-03-10T15:15:00Z"),
        rows=[
            {
                "row_number": 2,
                "raw_values": [
                    "MC222222",
                    "22223333",
                    "82",
                    "BI&PD",
                    "Acme Insurance",
                    "POL-123",
                    "03/01/2026",
                    "0",
                    "1000",
                    "03/10/2026",
                    "04/10/2026",
                ],
                "raw_fields": {
                    "Docket Number": "MC222222",
                    "USDOT Number": "22223333",
                    "Form Code": "82",
                    "Insurance Type Description": "BI&PD",
                    "Insurance Company Name": "Acme Insurance",
                    "Policy Number": "POL-123",
                    "Posted Date": "03/01/2026",
                    "BI&PD Underlying Limit": "0",
                    "BI&PD Maximum Limit": "1000",
                    "Effective Date": "03/10/2026",
                    "Cancel Effective Date": "04/10/2026",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["insurance_policy_filings"].values()))
    assert stored["posted_date"] == "2026-03-01"
    assert stored["bipd_maximum_limit_thousands_usd"] == 1000


def test_upsert_insurance_policy_history_events_persists_typed_row(fake_client: _FakeSupabaseClient):
    result = upsert_insurance_policy_history_events(
        source_context=_source_context(feed_name="InsHist", observed_at="2026-03-10T15:20:00Z"),
        rows=[
            {
                "row_number": 3,
                "raw_values": [
                    "MC333333",
                    "33334444",
                    "91X",
                    "Cancelled",
                    "35",
                    " ",
                    "BIPD/Primary",
                    "TP404896",
                    "750",
                    "P",
                    "09/01/1991",
                    "0",
                    "1000",
                    "09/01/1995",
                    "CANCEL",
                    "00",
                    "FIRE & CASUALTY INSURANCE CO. OF CONNECTICUT",
                ],
                "raw_fields": {
                    "Docket Number": "MC333333",
                    "USDOT Number": "33334444",
                    "Form Code": "91X",
                    "Cancellation Method": "Cancelled",
                    "Cancel/Replace/Name Change/Transfer Form": "35",
                    "Insurance Type Indicator": " ",
                    "Insurance Type Description": "BIPD/Primary",
                    "Policy Number": "TP404896",
                    "Minimum Coverage Amount": "750",
                    "Insurance Class Code": "P",
                    "Effective Date": "09/01/1991",
                    "BI&PD Underlying Limit Amount": "0",
                    "BI&PD Max Coverage Amount": "1000",
                    "Cancel Effective Date": "09/01/1995",
                    "Specific Cancellation Method": "CANCEL",
                    "Insurance Company Branch": "00",
                    "Insurance Company Name": "FIRE & CASUALTY INSURANCE CO. OF CONNECTICUT",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["insurance_policy_history_events"].values()))
    assert stored["minimum_coverage_amount_thousands_usd"] == 750
    assert stored["cancel_effective_date"] == "1995-09-01"


@pytest.mark.asyncio
async def test_internal_operating_authority_revocations_endpoint_passes_batch_to_service(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def _upsert_operating_authority_revocations(*, source_context: dict, rows: list[dict]):
        captured["source_context"] = source_context
        captured["rows"] = rows
        return {
            "feed_name": source_context["feed_name"],
            "rows_received": len(rows),
            "rows_written": len(rows),
        }

    monkeypatch.setattr(
        internal,
        "upsert_operating_authority_revocations",
        _upsert_operating_authority_revocations,
    )

    payload = internal.InternalUpsertFmcsaDailyDiffBatchRequest(
        feed_name="Revocation",
        download_url="https://data.transportation.gov/download/pivg-szje/text%2Fplain",
        source_file_variant="daily diff",
        source_observed_at="2026-03-10T15:05:00Z",
        source_task_id="fmcsa-revocation-daily",
        source_schedule_id="schedule-1",
        source_run_metadata={"run": "revocation"},
        records=[
            internal.InternalFmcsaDailyDiffRow(
                row_number=1,
                raw_values=[
                    "MC999999",
                    "87654321",
                    "Broker",
                    "03/08/2026",
                    "Insurance",
                    "03/10/2026",
                ],
                raw_fields={
                    "Docket Number": "MC999999",
                    "USDOT Number": "87654321",
                    "Operating Authority Registration Type": "Broker",
                    "Serve Date": "03/08/2026",
                    "Revocation Type": "Insurance",
                    "Effective Date": "03/10/2026",
                },
            )
        ],
    )

    response = await internal.internal_upsert_operating_authority_revocations(payload, None)

    assert response.data["feed_name"] == "Revocation"
    assert response.data["rows_written"] == 1
    assert captured["source_context"] == {
        "feed_name": "Revocation",
        "download_url": "https://data.transportation.gov/download/pivg-szje/text%2Fplain",
        "source_file_variant": "daily diff",
        "source_observed_at": "2026-03-10T15:05:00Z",
        "source_task_id": "fmcsa-revocation-daily",
        "source_schedule_id": "schedule-1",
        "source_run_metadata": {"run": "revocation"},
    }
    assert len(captured["rows"]) == 1
