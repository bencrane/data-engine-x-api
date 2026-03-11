from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.routers import internal
from app.services.carrier_registrations import upsert_carrier_registrations
from app.services import fmcsa_daily_diff_common
from app.services.insurance_filing_rejections import upsert_insurance_filing_rejections
from app.services.insurance_policies import upsert_insurance_policies
from app.services.insurance_policy_filings import upsert_insurance_policy_filings
from app.services.insurance_policy_history_events import upsert_insurance_policy_history_events
from app.services.operating_authority_histories import upsert_operating_authority_histories
from app.services.operating_authority_revocations import upsert_operating_authority_revocations
from app.services.process_agent_filings import upsert_process_agent_filings


@dataclass
class _Result:
    data: list[dict]


class _FakeTableQuery:
    def __init__(self, client: "_FakeSupabaseClient", table_name: str):
        self.client = client
        self.table_name = table_name
        self.mode: str | None = None
        self.upsert_rows: list[dict] = []

    def upsert(self, rows: list[dict], on_conflict: str):
        assert on_conflict == "feed_date,source_feed_name,row_position"
        self.mode = "upsert"
        self.upsert_rows = rows
        return self

    def execute(self):
        table = self.client.tables.setdefault(self.table_name, {})

        if self.mode == "upsert":
            persisted_rows = []
            for row in self.upsert_rows:
                identity = (row["feed_date"], row["source_feed_name"], row["row_position"])
                existing = table.get(identity)
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
                table[identity] = stored
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
        "feed_date": observed_at[:10],
        "download_url": f"https://example.com/{feed_name.lower()}",
        "source_file_variant": "daily diff",
        "source_observed_at": observed_at,
        "source_task_id": f"{feed_name.lower()}-task",
        "source_schedule_id": f"{feed_name.lower()}-schedule",
        "source_run_metadata": {"run": feed_name},
    }


def test_upsert_carrier_registrations_preserves_snapshot_row(fake_client: _FakeSupabaseClient):
    result = upsert_carrier_registrations(
        source_context=_source_context(feed_name="Carrier", observed_at="2026-03-10T15:00:00Z"),
        rows=[
            {
                "row_number": 4,
                "raw_values": [
                    "MC444444",
                    "12345678",
                    "",
                    "",
                    "A",
                    "N",
                    "I",
                    "N",
                    "N",
                    "Y",
                    "N",
                    "N",
                    "Y",
                    "Y",
                    "N",
                    "N",
                    "N",
                    "Y",
                    "00750",
                    "N",
                    "Y",
                    "01000",
                    "N",
                    "Y",
                    "Y",
                    "ACME LOGISTICS",
                    "ACME LOGISTICS LLC",
                    "123 MAIN ST",
                    "",
                    "AUSTIN",
                    "TX",
                    "US",
                    "78701",
                    "5125550101",
                    "",
                    "PO BOX 5",
                    "",
                    "AUSTIN",
                    "TX",
                    "US",
                    "78702",
                    "5125550102",
                    "",
                ],
                "raw_fields": {
                    "Docket Number": "MC444444",
                    "USDOT Number": "12345678",
                    "MX Type": "",
                    "RFC Number": "",
                    "Common Authority": "A",
                    "Contract Authority": "N",
                    "Broker Authority": "I",
                    "Pending Common Authority": "N",
                    "Pending Contract Authority": "N",
                    "Pending Broker Authority": "Y",
                    "Common Authority Revocation": "N",
                    "Contract Authority Revocation": "N",
                    "Broker Authority Revocation": "Y",
                    "Property": "Y",
                    "Passenger": "N",
                    "Household Goods": "N",
                    "Private Check": "N",
                    "Enterprise Check": "Y",
                    "BIPD Required": "00750",
                    "Cargo Required": "N",
                    "Bond/Surety Required": "Y",
                    "BIPD on File": "01000",
                    "Cargo on File": "N",
                    "Bond/Surety on File": "Y",
                    "Address Status": "Y",
                    "DBA Name": "ACME LOGISTICS",
                    "Legal Name": "ACME LOGISTICS LLC",
                    "Business Address - PO Box/Street": "123 MAIN ST",
                    "Business Address - Colonia": "",
                    "Business Address - City": "AUSTIN",
                    "Business Address - State Code": "TX",
                    "Business Address - Country Code": "US",
                    "Business Address - Zip Code": "78701",
                    "Business Address - Telephone Number": "5125550101",
                    "Business Address - Fax Number": "",
                    "Mailing Address - PO Box/Street": "PO BOX 5",
                    "Mailing Address - Colonia": "",
                    "Mailing Address - City": "AUSTIN",
                    "Mailing Address - State Code": "TX",
                    "Mailing Address - Country Code": "US",
                    "Mailing Address - Zip Code": "78702",
                    "Mailing Address - Telephone Number": "5125550102",
                    "Mailing Address - Fax Number": "",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["carrier_registrations"].values()))
    assert stored["docket_number"] == "MC444444"
    assert stored["bipd_required_thousands_usd"] == 750
    assert stored["business_address_city"] == "AUSTIN"
    assert stored["raw_source_row"]["row_number"] == 4


def test_upsert_process_agent_filings_same_day_rerun_updates_same_feed_slot(
    fake_client: _FakeSupabaseClient,
):
    first_row = {
        "row_number": 1,
        "raw_values": ["MC555555", "55556666", "AGENT ONE", "LEGAL", "1 MAIN", "AUSTIN", "TX", "USA", "78701"],
        "raw_fields": {
            "Docket Number": "MC555555",
            "USDOT Number": "55556666",
            "Company Name": "AGENT ONE",
            "Attention to or Title": "LEGAL",
            "Street or PO Box": "1 MAIN",
            "City": "AUSTIN",
            "State": "TX",
            "Country": "USA",
            "Zip Code": "78701",
        },
    }
    second_row = {
        "row_number": 1,
        "raw_values": ["MC555555", "55556666", "AGENT TWO", "LEGAL", "1 MAIN", "AUSTIN", "TX", "USA", "78701"],
        "raw_fields": {
            "Docket Number": "MC555555",
            "USDOT Number": "55556666",
            "Company Name": "AGENT TWO",
            "Attention to or Title": "LEGAL",
            "Street or PO Box": "1 MAIN",
            "City": "AUSTIN",
            "State": "TX",
            "Country": "USA",
            "Zip Code": "78701",
        },
    }

    upsert_process_agent_filings(
        source_context=_source_context(feed_name="BOC3", observed_at="2026-03-10T15:05:00Z"),
        rows=[first_row],
    )
    upsert_process_agent_filings(
        source_context=_source_context(feed_name="BOC3", observed_at="2026-03-10T15:06:00Z"),
        rows=[second_row],
    )

    assert len(fake_client.tables["process_agent_filings"]) == 1
    stored = next(iter(fake_client.tables["process_agent_filings"].values()))
    assert stored["process_agent_company_name"] == "AGENT TWO"
    assert stored["source_feed_name"] == "BOC3"


def test_shared_table_keeps_daily_and_all_history_rows_separate_on_same_feed_date(
    fake_client: _FakeSupabaseClient,
):
    row = {
        "row_number": 1,
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

    upsert_insurance_policy_history_events(
        source_context=_source_context(feed_name="InsHist", observed_at="2026-03-10T15:20:00Z"),
        rows=[row],
    )
    upsert_insurance_policy_history_events(
        source_context=_source_context(
            feed_name="InsHist - All With History",
            observed_at="2026-03-10T16:20:00Z",
        ),
        rows=[row],
    )

    assert len(fake_client.tables["insurance_policy_history_events"]) == 2
    stored_rows = list(fake_client.tables["insurance_policy_history_events"].values())
    assert {stored["source_feed_name"] for stored in stored_rows} == {
        "InsHist",
        "InsHist - All With History",
    }


def test_upsert_insurance_filing_rejections_persists_typed_row(fake_client: _FakeSupabaseClient):
    result = upsert_insurance_filing_rejections(
        source_context=_source_context(feed_name="Rejected", observed_at="2026-03-10T15:25:00Z"),
        rows=[
            {
                "row_number": 5,
                "raw_values": [
                    "MC888888",
                    "88889999",
                    "82",
                    "BI&PD",
                    "POL-888",
                    "03/01/2026",
                    "P",
                    " ",
                    "0",
                    "750",
                    "03/03/2026",
                    "07",
                    "ACME INSURANCE",
                    "Policy is already cancelled",
                    "750",
                ],
                "raw_fields": {
                    "Docket Number": "MC888888",
                    "USDOT Number": "88889999",
                    "Form Code (Insurance or Cancel)": "82",
                    "Insurance Type Description": "BI&PD",
                    "Policy Number": "POL-888",
                    "Received Date": "03/01/2026",
                    "Insurance Class Code": "P",
                    "Insurance Type Code": " ",
                    "Underlying Limit Amount": "0",
                    "Maximum Coverage Amount": "750",
                    "Rejected Date": "03/03/2026",
                    "Insurance Branch": "07",
                    "Company Name": "ACME INSURANCE",
                    "Rejected Reason": "Policy is already cancelled",
                    "Minimum Coverage Amount": "750",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["insurance_filing_rejections"].values()))
    assert stored["rejected_date"] == "2026-03-03"
    assert stored["insurance_company_name"] == "ACME INSURANCE"
    assert stored["rejected_reason"] == "Policy is already cancelled"


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


def test_upsert_operating_authority_revocations_stores_one_row_per_feed_date(
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

    monday_result = upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-10T15:05:00Z"),
        rows=[row],
    )
    tuesday_result = upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-11T15:05:00Z"),
        rows=[row],
    )

    assert monday_result["rows_written"] == 1
    assert tuesday_result["rows_written"] == 1
    assert len(fake_client.tables["operating_authority_revocations"]) == 2

    stored_rows = list(fake_client.tables["operating_authority_revocations"].values())
    assert {row["feed_date"] for row in stored_rows} == {"2026-03-10", "2026-03-11"}
    assert all(row["row_position"] == 1 for row in stored_rows)


def test_upsert_operating_authority_revocations_same_day_rerun_updates_same_position(
    fake_client: _FakeSupabaseClient,
):
    first_row = {
        "row_number": 1,
        "raw_values": ["MC999999", "87654321", "Broker", "03/08/2026", "Insurance", "03/10/2026"],
        "raw_fields": {
            "Docket Number": "MC999999",
            "USDOT Number": "87654321",
            "Operating Authority Registration Type": "Broker",
            "Serve Date": "03/08/2026",
            "Revocation Type": "Insurance",
            "Effective Date": "03/10/2026",
        },
    }
    second_row = {
        "row_number": 1,
        "raw_values": ["MC999999", "87654321", "Broker", "03/08/2026", "Safety", "03/10/2026"],
        "raw_fields": {
            "Docket Number": "MC999999",
            "USDOT Number": "87654321",
            "Operating Authority Registration Type": "Broker",
            "Serve Date": "03/08/2026",
            "Revocation Type": "Safety",
            "Effective Date": "03/10/2026",
        },
    }

    upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-10T15:05:00Z"),
        rows=[first_row],
    )
    upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-10T15:06:00Z"),
        rows=[second_row],
    )

    assert len(fake_client.tables["operating_authority_revocations"]) == 1
    stored = next(iter(fake_client.tables["operating_authority_revocations"].values()))
    assert stored["feed_date"] == "2026-03-10"
    assert stored["row_position"] == 1
    assert stored["revocation_type"] == "Safety"


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
        feed_date="2026-03-10",
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
        "feed_date": "2026-03-10",
        "download_url": "https://data.transportation.gov/download/pivg-szje/text%2Fplain",
        "source_file_variant": "daily diff",
        "source_observed_at": "2026-03-10T15:05:00Z",
        "source_task_id": "fmcsa-revocation-daily",
        "source_schedule_id": "schedule-1",
        "source_run_metadata": {"run": "revocation"},
    }
    assert len(captured["rows"]) == 1


@pytest.mark.asyncio
async def test_internal_process_agent_filings_endpoint_passes_batch_to_service(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def _upsert_process_agent_filings(*, source_context: dict, rows: list[dict]):
        captured["source_context"] = source_context
        captured["rows"] = rows
        return {
            "feed_name": source_context["feed_name"],
            "rows_received": len(rows),
            "rows_written": len(rows),
        }

    monkeypatch.setattr(
        internal,
        "upsert_process_agent_filings",
        _upsert_process_agent_filings,
    )

    payload = internal.InternalUpsertFmcsaDailyDiffBatchRequest(
        feed_name="BOC3 - All With History",
        feed_date="2026-03-10",
        download_url="https://data.transportation.gov/download/gmxu-awv7/text%2Fplain",
        source_file_variant="all_with_history",
        source_observed_at="2026-03-10T15:35:00Z",
        source_task_id="fmcsa-boc3-all-history",
        source_schedule_id="schedule-boc3-history",
        source_run_metadata={"run": "boc3-history"},
        records=[
            internal.InternalFmcsaDailyDiffRow(
                row_number=1,
                raw_values=[
                    "MC999111",
                    "11119999",
                    "AGENT CO",
                    "LEGAL",
                    "1 MAIN",
                    "AUSTIN",
                    "TX",
                    "USA",
                    "78701",
                ],
                raw_fields={
                    "Docket Number": "MC999111",
                    "USDOT Number": "11119999",
                    "Company Name": "AGENT CO",
                    "Attention to or Title": "LEGAL",
                    "Street or PO Box": "1 MAIN",
                    "City": "AUSTIN",
                    "State": "TX",
                    "Country": "USA",
                    "Zip Code": "78701",
                },
            )
        ],
    )

    response = await internal.internal_upsert_process_agent_filings(payload, None)

    assert response.data["feed_name"] == "BOC3 - All With History"
    assert response.data["rows_written"] == 1
    assert captured["source_context"] == {
        "feed_name": "BOC3 - All With History",
        "feed_date": "2026-03-10",
        "download_url": "https://data.transportation.gov/download/gmxu-awv7/text%2Fplain",
        "source_file_variant": "all_with_history",
        "source_observed_at": "2026-03-10T15:35:00Z",
        "source_task_id": "fmcsa-boc3-all-history",
        "source_schedule_id": "schedule-boc3-history",
        "source_run_metadata": {"run": "boc3-history"},
    }
    assert len(captured["rows"]) == 1


@pytest.mark.asyncio
async def test_internal_insurance_filing_rejections_endpoint_passes_batch_to_service(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def _upsert_insurance_filing_rejections(*, source_context: dict, rows: list[dict]):
        captured["source_context"] = source_context
        captured["rows"] = rows
        return {
            "feed_name": source_context["feed_name"],
            "rows_received": len(rows),
            "rows_written": len(rows),
        }

    monkeypatch.setattr(
        internal,
        "upsert_insurance_filing_rejections",
        _upsert_insurance_filing_rejections,
    )

    payload = internal.InternalUpsertFmcsaDailyDiffBatchRequest(
        feed_name="Rejected",
        feed_date="2026-03-10",
        download_url="https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain",
        source_file_variant="daily",
        source_observed_at="2026-03-10T15:45:00Z",
        source_task_id="fmcsa-rejected-daily",
        source_schedule_id="schedule-rejected",
        source_run_metadata={"run": "rejected"},
        records=[
            internal.InternalFmcsaDailyDiffRow(
                row_number=1,
                raw_values=[
                    "MC111000",
                    "00011122",
                    "82",
                    "BI&PD",
                    "POL-22",
                    "03/01/2026",
                    "P",
                    " ",
                    "0",
                    "750",
                    "03/04/2026",
                    "01",
                    "ACME INS",
                    "Missing signature",
                    "750",
                ],
                raw_fields={
                    "Docket Number": "MC111000",
                    "USDOT Number": "00011122",
                    "Form Code (Insurance or Cancel)": "82",
                    "Insurance Type Description": "BI&PD",
                    "Policy Number": "POL-22",
                    "Received Date": "03/01/2026",
                    "Insurance Class Code": "P",
                    "Insurance Type Code": " ",
                    "Underlying Limit Amount": "0",
                    "Maximum Coverage Amount": "750",
                    "Rejected Date": "03/04/2026",
                    "Insurance Branch": "01",
                    "Company Name": "ACME INS",
                    "Rejected Reason": "Missing signature",
                    "Minimum Coverage Amount": "750",
                },
            )
        ],
    )

    response = await internal.internal_upsert_insurance_filing_rejections(payload, None)

    assert response.data["feed_name"] == "Rejected"
    assert response.data["rows_written"] == 1
    assert captured["source_context"] == {
        "feed_name": "Rejected",
        "feed_date": "2026-03-10",
        "download_url": "https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain",
        "source_file_variant": "daily",
        "source_observed_at": "2026-03-10T15:45:00Z",
        "source_task_id": "fmcsa-rejected-daily",
        "source_schedule_id": "schedule-rejected",
        "source_run_metadata": {"run": "rejected"},
    }
    assert len(captured["rows"]) == 1
