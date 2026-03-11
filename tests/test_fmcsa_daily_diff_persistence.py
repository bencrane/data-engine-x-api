from __future__ import annotations

from dataclasses import dataclass
import re

import pytest

from app.routers import internal
from app.services.carrier_registrations import upsert_carrier_registrations
from app.services.carrier_inspections import upsert_carrier_inspections
from app.services.carrier_inspection_violations import upsert_carrier_inspection_violations
from app.services.carrier_safety_basic_measures import upsert_carrier_safety_basic_measures
from app.services.carrier_safety_basic_percentiles import upsert_carrier_safety_basic_percentiles
from app.services.commercial_vehicle_crashes import upsert_commercial_vehicle_crashes
from app.services import fmcsa_daily_diff_common
from app.services.insurance_filing_rejections import upsert_insurance_filing_rejections
from app.services.insurance_policies import upsert_insurance_policies
from app.services.insurance_policy_filings import upsert_insurance_policy_filings
from app.services.insurance_policy_history_events import upsert_insurance_policy_history_events
from app.services.motor_carrier_census_records import upsert_motor_carrier_census_records
from app.services.operating_authority_histories import upsert_operating_authority_histories
from app.services.operating_authority_revocations import upsert_operating_authority_revocations
from app.services.out_of_service_orders import upsert_out_of_service_orders
from app.services.process_agent_filings import upsert_process_agent_filings
from app.services.vehicle_inspection_citations import upsert_vehicle_inspection_citations
from app.services.vehicle_inspection_special_studies import upsert_vehicle_inspection_special_studies
from app.services.vehicle_inspection_units import upsert_vehicle_inspection_units


@dataclass
class _FakeDirectPostgresDatabase:
    tables: dict[str, dict[tuple[object, ...], dict]]
    table_columns: dict[str, tuple[str, ...]]

    def __init__(self):
        self.tables = {}
        self.table_columns = {}


def _default_table_columns(table_name: str) -> tuple[str, ...]:
    return ()


def _unwrap_postgres_value(value):
    return getattr(value, "obj", value)


class _FakeDirectPostgresCursor:
    def __init__(self, database: _FakeDirectPostgresDatabase):
        self.database = database
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params: tuple[str, str]):
        if "information_schema.columns" not in query:
            raise AssertionError(f"Unsupported execute query in fake cursor: {query}")
        schema_name, table_name = params
        assert schema_name == "entities"
        self._last_fetchall = [
            (column_name,)
            for column_name in self.database.table_columns.get(
                table_name, _default_table_columns(table_name)
            )
        ]
        return self

    def fetchall(self):
        return getattr(self, "_last_fetchall", [])

    def executemany(self, query: str, params_seq: list[dict]):
        table_match = re.search(r'INSERT INTO "entities"\."([^"]+)"', query)
        if table_match is None:
            raise AssertionError(f"Could not parse target table from query: {query}")
        table_name = table_match.group(1)
        conflict_match = re.search(r"ON CONFLICT \(([^)]+)\)", query)
        if conflict_match is None:
            raise AssertionError(f"Could not parse conflict target from query: {query}")
        conflict_columns = tuple(
            column_name.strip().strip('"')
            for column_name in conflict_match.group(1).split(",")
        )
        table = self.database.tables.setdefault(table_name, {})
        self.rowcount = 0

        for params in params_seq:
            normalized = {key: _unwrap_postgres_value(value) for key, value in params.items()}
            identity = tuple(normalized[column_name] for column_name in conflict_columns)
            existing = table.get(identity)
            if existing is None:
                stored = {
                    "id": f"{table_name}-{len(table) + 1}",
                    "created_at": normalized.get("updated_at"),
                    **normalized,
                }
            else:
                stored = {
                    **existing,
                    **{
                        key: value
                        for key, value in normalized.items()
                        if key not in fmcsa_daily_diff_common.FMCSA_INSERT_ONLY_ON_CONFLICT_COLUMNS
                    },
                    "created_at": existing["created_at"],
                }
                for key in fmcsa_daily_diff_common.FMCSA_INSERT_ONLY_ON_CONFLICT_COLUMNS:
                    if key in existing:
                        stored[key] = existing[key]
            table[identity] = stored
            self.rowcount += 1


class _FakeDirectPostgresConnection:
    def __init__(self, database: _FakeDirectPostgresDatabase):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeDirectPostgresCursor(self.database)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeDirectPostgresDatabase:
    database = _FakeDirectPostgresDatabase()
    fmcsa_daily_diff_common._get_table_columns.cache_clear()
    monkeypatch.setattr(
        fmcsa_daily_diff_common,
        "get_fmcsa_direct_postgres_connection",
        lambda: _FakeDirectPostgresConnection(database),
    )
    return database


def _source_context(
    *,
    feed_name: str,
    observed_at: str,
    source_file_variant: str = "daily diff",
) -> dict:
    return {
        "feed_name": feed_name,
        "feed_date": observed_at[:10],
        "download_url": f"https://example.com/{feed_name.lower()}",
        "source_file_variant": source_file_variant,
        "source_observed_at": observed_at,
        "source_task_id": f"{feed_name.lower()}-task",
        "source_schedule_id": f"{feed_name.lower()}-schedule",
        "source_run_metadata": {"run": feed_name},
    }


def test_get_fmcsa_direct_postgres_connection_uses_database_url(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: dict[str, object] = {}

    def _connect(database_url: str):
        captured["database_url"] = database_url
        return object()

    monkeypatch.setattr(fmcsa_daily_diff_common, "connect", _connect)
    monkeypatch.setattr(
        fmcsa_daily_diff_common,
        "get_settings",
        lambda: type("Settings", (), {"database_url": "postgresql://fmcsa:test@localhost:5432/app"})(),
    )

    connection = fmcsa_daily_diff_common.get_fmcsa_direct_postgres_connection()

    assert connection is not None
    assert captured["database_url"] == "postgresql://fmcsa:test@localhost:5432/app"


def test_top5_tables_fall_back_to_live_legacy_columns_when_snapshot_columns_absent(
    fake_client: _FakeDirectPostgresDatabase,
):
    fake_client.table_columns["operating_authority_histories"] = (
        "record_fingerprint",
        "docket_number",
        "usdot_number",
        "sub_number",
        "operating_authority_type",
        "original_authority_action_description",
        "original_authority_action_served_date",
        "final_authority_action_description",
        "final_authority_decision_date",
        "final_authority_served_date",
        "source_provider",
        "source_feed_name",
        "source_download_url",
        "source_file_variant",
        "source_observed_at",
        "source_task_id",
        "source_schedule_id",
        "source_run_metadata",
        "raw_source_row",
        "first_observed_at",
        "last_observed_at",
        "updated_at",
    )

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

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["operating_authority_histories"].values()))
    assert "feed_date" not in stored
    assert "row_position" not in stored
    assert stored["record_fingerprint"]
    assert stored["first_observed_at"] == "2026-03-10T15:00:00Z"
    assert stored["last_observed_at"] == "2026-03-10T15:00:00Z"


def test_top5_tables_use_record_fingerprint_conflict_when_live_schema_is_legacy(
    fake_client: _FakeDirectPostgresDatabase,
):
    fake_client.table_columns["insurance_policy_history_events"] = (
        "record_fingerprint",
        "docket_number",
        "usdot_number",
        "form_code",
        "cancellation_method",
        "cancellation_form_code",
        "insurance_type_indicator",
        "insurance_type_description",
        "policy_number",
        "minimum_coverage_amount_thousands_usd",
        "insurance_class_code",
        "effective_date",
        "bipd_underlying_limit_amount_thousands_usd",
        "bipd_max_coverage_amount_thousands_usd",
        "cancel_effective_date",
        "specific_cancellation_method",
        "insurance_company_branch",
        "insurance_company_name",
        "source_provider",
        "source_feed_name",
        "source_download_url",
        "source_file_variant",
        "source_observed_at",
        "source_task_id",
        "source_schedule_id",
        "source_run_metadata",
        "raw_source_row",
        "first_observed_at",
        "last_observed_at",
        "updated_at",
    )

    first_row = {
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
    second_row = {
        **first_row,
        "raw_fields": {
            **first_row["raw_fields"],
            "Cancellation Method": "Reinstated",
        },
    }

    upsert_insurance_policy_history_events(
        source_context=_source_context(feed_name="InsHist", observed_at="2026-03-10T15:20:00Z"),
        rows=[first_row],
    )
    upsert_insurance_policy_history_events(
        source_context=_source_context(feed_name="InsHist", observed_at="2026-03-10T15:21:00Z"),
        rows=[second_row],
    )

    assert len(fake_client.tables["insurance_policy_history_events"]) == 1
    stored = next(iter(fake_client.tables["insurance_policy_history_events"].values()))
    assert stored["cancellation_method"] == "Reinstated"
    assert stored["first_observed_at"] == "2026-03-10T15:20:00Z"
    assert stored["last_observed_at"] == "2026-03-10T15:21:00Z"


def test_upsert_carrier_registrations_preserves_snapshot_row(fake_client: _FakeDirectPostgresDatabase):
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


def test_upsert_commercial_vehicle_crashes_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
    result = upsert_commercial_vehicle_crashes(
        source_context=_source_context(feed_name="Crash File", observed_at="2026-03-10T14:00:00Z"),
        rows=[
            {
                "row_number": 1,
                "raw_values": [
                    "19901102 0000",
                    "195291",
                    "VA",
                    "VA00000875",
                    "19900118",
                    "0900",
                    "1",
                    "12345678",
                    "C",
                    "19900120",
                    "I-95",
                    "00000",
                    "RICHMOND",
                    "VA",
                    "001",
                    "T",
                    "1",
                    "1",
                    "1",
                    "3",
                    "3",
                    "VIN12345678901234",
                    "ABC1234",
                    "VA",
                    "Y",
                    "1",
                    "9",
                    "1",
                    "N",
                    "STATE POLICE",
                    "2",
                    "0",
                    "1",
                    "Y",
                    "Y",
                    "Y",
                    "1.0",
                    "1234",
                    "A",
                    "19900119 1015",
                    "0",
                    "12345678",
                    "Y",
                    "19900119 1100",
                    "19900119 1115",
                    "999",
                    "ACME CARRIER",
                    "1 MAIN ST",
                    "RICHMOND",
                    "00000",
                    "VA",
                    "23219",
                    "",
                    "MC123456",
                    "Y",
                    "",
                    "",
                    "",
                    "1:13:Collision involving motor vehicle in transport",
                ],
                "raw_fields": {
                    "CHANGE_DATE": "19901102 0000",
                    "CRASH_ID": "195291",
                    "REPORT_STATE": "VA",
                    "REPORT_NUMBER": "VA00000875",
                    "REPORT_DATE": "19900118",
                    "REPORT_TIME": "0900",
                    "REPORT_SEQ_NO": "1",
                    "DOT_NUMBER": "12345678",
                    "CI_STATUS_CODE": "C",
                    "FINAL_STATUS_DATE": "19900120",
                    "LOCATION": "I-95",
                    "CITY_CODE": "00000",
                    "CITY": "RICHMOND",
                    "STATE": "VA",
                    "COUNTY_CODE": "001",
                    "TRUCK_BUS_IND": "T",
                    "TRAFFICWAY_ID": "1",
                    "ACCESS_CONTROL_ID": "1",
                    "ROAD_SURFACE_CONDITION_ID": "1",
                    "CARGO_BODY_TYPE_ID": "3",
                    "GVW_RATING_ID": "3",
                    "VEHICLE_IDENTIFICATION_NUMBER": "VIN12345678901234",
                    "VEHICLE_LICENSE_NUMBER": "ABC1234",
                    "VEHICLE_LIC_STATE": "VA",
                    "VEHICLE_HAZMAT_PLACARD": "Y",
                    "WEATHER_CONDITION_ID": "1",
                    "VEHICLE_CONFIGURATION_ID": "9",
                    "LIGHT_CONDITION_ID": "1",
                    "HAZMAT_RELEASED": "N",
                    "AGENCY": "STATE POLICE",
                    "VEHICLES_IN_ACCIDENT": "2",
                    "FATALITIES": "0",
                    "INJURIES": "1",
                    "TOW_AWAY": "Y",
                    "FEDERAL_RECORDABLE": "Y",
                    "STATE_RECORDABLE": "Y",
                    "SNET_VERSION_NUMBER": "1.0",
                    "SNET_SEQUENCE_ID": "1234",
                    "TRANSACTION_CODE": "A",
                    "TRANSACTION_DATE": "19900119 1015",
                    "UPLOAD_FIRST_BYTE": "0",
                    "UPLOAD_DOT_NUMBER": "12345678",
                    "UPLOAD_SEARCH_INDICATOR": "Y",
                    "UPLOAD_DATE": "19900119 1100",
                    "ADD_DATE": "19900119 1115",
                    "CRASH_CARRIER_ID": "999",
                    "CRASH_CARRIER_NAME": "ACME CARRIER",
                    "CRASH_CARRIER_STREET": "1 MAIN ST",
                    "CRASH_CARRIER_CITY": "RICHMOND",
                    "CRASH_CARRIER_CITY_CODE": "00000",
                    "CRASH_CARRIER_STATE": "VA",
                    "CRASH_CARRIER_ZIP_CODE": "23219",
                    "CRASH_COLONIA": "",
                    "DOCKET_NUMBER": "MC123456",
                    "CRASH_CARRIER_INTERSTATE": "Y",
                    "NO_ID_FLAG": "",
                    "STATE_NUMBER": "",
                    "STATE_ISSUING_NUMBER": "",
                    "CRASH_EVENT_SEQ_ID_DESC": "1:13:Collision involving motor vehicle in transport",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["commercial_vehicle_crashes"].values()))
    assert stored["crash_id"] == "195291"
    assert stored["report_date"] == "1990-01-18"
    assert stored["tow_away"] is True


def test_shared_carrier_registration_table_keeps_daily_and_all_history_rows_separate(
    fake_client: _FakeDirectPostgresDatabase,
):
    row = {
        "row_number": 1,
        "raw_values": [
            "MC012892",
            "02217388",
            "",
            "",
            "N",
            "A",
            "N",
            "N",
            "N",
            "N",
            "N",
            "N",
            "N",
            "Y",
            "N",
            "N",
            "N",
            "N",
            "00750",
            "N",
            "N",
            "00750",
            "N",
            "N",
            "Y",
            "",
            "ACME CARRIER LLC",
            "1 MAIN ST",
            "",
            "AUSTIN",
            "TX",
            "US",
            "78701",
            "5125550000",
            "",
            "1 MAIN ST",
            "",
            "AUSTIN",
            "TX",
            "US",
            "78701",
            "5125550000",
            "",
        ],
        "raw_fields": {
            "Docket Number": "MC012892",
            "USDOT Number": "02217388",
            "MX Type": "",
            "RFC Number": "",
            "Common Authority": "N",
            "Contract Authority": "A",
            "Broker Authority": "N",
            "Pending Common Authority": "N",
            "Pending Contract Authority": "N",
            "Pending Broker Authority": "N",
            "Common Authority Revocation": "N",
            "Contract Authority Revocation": "N",
            "Broker Authority Revocation": "N",
            "Property": "Y",
            "Passenger": "N",
            "Household Goods": "N",
            "Private Check": "N",
            "Enterprise Check": "N",
            "BIPD Required": "00750",
            "Cargo Required": "N",
            "Bond/Surety Required": "N",
            "BIPD on File": "00750",
            "Cargo on File": "N",
            "Bond/Surety on File": "N",
            "Address Status": "Y",
            "DBA Name": "",
            "Legal Name": "ACME CARRIER LLC",
            "Business Address - PO Box/Street": "1 MAIN ST",
            "Business Address - Colonia": "",
            "Business Address - City": "AUSTIN",
            "Business Address - State Code": "TX",
            "Business Address - Country Code": "US",
            "Business Address - Zip Code": "78701",
            "Business Address - Telephone Number": "5125550000",
            "Business Address - Fax Number": "",
            "Mailing Address - PO Box/Street": "1 MAIN ST",
            "Mailing Address - Colonia": "",
            "Mailing Address - City": "AUSTIN",
            "Mailing Address - State Code": "TX",
            "Mailing Address - Country Code": "US",
            "Mailing Address - Zip Code": "78701",
            "Mailing Address - Telephone Number": "5125550000",
            "Mailing Address - Fax Number": "",
        },
    }

    upsert_carrier_registrations(
        source_context=_source_context(feed_name="Carrier", observed_at="2026-03-10T10:00:00Z"),
        rows=[row],
    )
    upsert_carrier_registrations(
        source_context=_source_context(
            feed_name="Carrier - All With History",
            observed_at="2026-03-10T11:00:00Z",
            source_file_variant="all_with_history",
        ),
        rows=[row],
    )

    assert len(fake_client.tables["carrier_registrations"]) == 2
    assert {stored["source_feed_name"] for stored in fake_client.tables["carrier_registrations"].values()} == {
        "Carrier",
        "Carrier - All With History",
    }


def test_upsert_process_agent_filings_same_day_rerun_updates_same_feed_slot(
    fake_client: _FakeDirectPostgresDatabase,
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
    first_created_at = next(iter(fake_client.tables["process_agent_filings"].values()))["created_at"]
    upsert_process_agent_filings(
        source_context=_source_context(feed_name="BOC3", observed_at="2026-03-10T15:06:00Z"),
        rows=[second_row],
    )

    assert len(fake_client.tables["process_agent_filings"]) == 1
    stored = next(iter(fake_client.tables["process_agent_filings"].values()))
    assert stored["process_agent_company_name"] == "AGENT TWO"
    assert stored["source_feed_name"] == "BOC3"
    assert stored["created_at"] == first_created_at
    assert stored["source_observed_at"] == "2026-03-10T15:06:00Z"
    assert stored["raw_source_row"]["raw_fields"]["Company Name"] == "AGENT TWO"


def test_upsert_carrier_safety_basic_measures_keeps_ab_and_c_rows_distinct(
    fake_client: _FakeDirectPostgresDatabase,
):
    row = {
        "row_number": 1,
        "raw_values": [
            "10000",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "0",
            "N",
            "0",
            "0",
            "N",
            "0",
            "0",
            "N",
            "0",
            "0",
            "N",
            "0",
            "0",
            "N",
        ],
        "raw_fields": {
            "DOT_NUMBER": "10000",
            "INSP_TOTAL": "0",
            "DRIVER_INSP_TOTAL": "0",
            "DRIVER_OOS_INSP_TOTAL": "0",
            "VEHICLE_INSP_TOTAL": "0",
            "VEHICLE_OOS_INSP_TOTAL": "0",
            "UNSAFE_DRIV_INSP_W_VIOL": "0",
            "UNSAFE_DRIV_MEASURE": "0",
            "UNSAFE_DRIV_AC": "N",
            "HOS_DRIV_INSP_W_VIOL": "0",
            "HOS_DRIV_MEASURE": "0",
            "HOS_DRIV_AC": "N",
            "DRIV_FIT_INSP_W_VIOL": "0",
            "DRIV_FIT_MEASURE": "0",
            "DRIV_FIT_AC": "N",
            "CONTR_SUBST_INSP_W_VIOL": "0",
            "CONTR_SUBST_MEASURE": "0",
            "CONTR_SUBST_AC": "N",
            "VEH_MAINT_INSP_W_VIOL": "0",
            "VEH_MAINT_MEASURE": "0",
            "VEH_MAINT_AC": "N",
        },
    }

    upsert_carrier_safety_basic_measures(
        source_context=_source_context(
            feed_name="SMS AB PassProperty",
            observed_at="2026-03-10T12:00:00Z",
            source_file_variant="csv_export",
        ),
        rows=[row],
    )
    upsert_carrier_safety_basic_measures(
        source_context=_source_context(
            feed_name="SMS C PassProperty",
            observed_at="2026-03-10T12:01:00Z",
            source_file_variant="csv_export",
        ),
        rows=[row],
    )

    assert len(fake_client.tables["carrier_safety_basic_measures"]) == 2
    stored_rows = list(fake_client.tables["carrier_safety_basic_measures"].values())
    assert {stored["carrier_segment"] for stored in stored_rows} == {
        "interstate_and_intrastate_hazmat_property_or_passenger",
        "intrastate_non_hazmat_property_or_passenger",
    }


def test_upsert_carrier_safety_basic_percentiles_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
    result = upsert_carrier_safety_basic_percentiles(
        source_context=_source_context(
            feed_name="SMS AB Pass",
            observed_at="2026-03-10T12:10:00Z",
            source_file_variant="csv_export",
        ),
        rows=[
            {
                "row_number": 1,
                "raw_values": [
                    "100115",
                    "68",
                    "52",
                    "0",
                    "51",
                    "1",
                    "3",
                    ".03",
                    "0%",
                    "N",
                    "N",
                    "N",
                    "2",
                    ".02",
                    "1%",
                    "N",
                    "N",
                    "N",
                    "1",
                    ".01",
                    "2%",
                    "N",
                    "N",
                    "N",
                    "0",
                    "0",
                    "0%",
                    "N",
                    "N",
                    "N",
                    "4",
                    ".25",
                    "15%",
                    "Y",
                    "N",
                    "Y",
                ],
                "raw_fields": {
                    "DOT_NUMBER": "100115",
                    "INSP_TOTAL": "68",
                    "DRIVER_INSP_TOTAL": "52",
                    "DRIVER_OOS_INSP_TOTAL": "0",
                    "VEHICLE_INSP_TOTAL": "51",
                    "VEHICLE_OOS_INSP_TOTAL": "1",
                    "UNSAFE_DRIV_INSP_W_VIOL": "3",
                    "UNSAFE_DRIV_MEASURE": ".03",
                    "UNSAFE_DRIV_PCT": "0%",
                    "UNSAFE_DRIV_RD_ALERT": "N",
                    "UNSAFE_DRIV_AC": "N",
                    "UNSAFE_DRIV_BASIC_ALERT": "N",
                    "HOS_DRIV_INSP_W_VIOL": "2",
                    "HOS_DRIV_MEASURE": ".02",
                    "HOS_DRIV_PCT": "1%",
                    "HOS_DRIV_RD_ALERT": "N",
                    "HOS_DRIV_AC": "N",
                    "HOS_DRIV_BASIC_ALERT": "N",
                    "DRIV_FIT_INSP_W_VIOL": "1",
                    "DRIV_FIT_MEASURE": ".01",
                    "DRIV_FIT_PCT": "2%",
                    "DRIV_FIT_RD_ALERT": "N",
                    "DRIV_FIT_AC": "N",
                    "DRIV_FIT_BASIC_ALERT": "N",
                    "CONTR_SUBST_INSP_W_VIOL": "0",
                    "CONTR_SUBST_MEASURE": "0",
                    "CONTR_SUBST_PCT": "0%",
                    "CONTR_SUBST_RD_ALERT": "N",
                    "CONTR_SUBST_AC": "N",
                    "CONTR_SUBST_BASIC_ALERT": "N",
                    "VEH_MAINT_INSP_W_VIOL": "4",
                    "VEH_MAINT_MEASURE": ".25",
                    "VEH_MAINT_PCT": "15%",
                    "VEH_MAINT_RD_ALERT": "Y",
                    "VEH_MAINT_AC": "N",
                    "VEH_MAINT_BASIC_ALERT": "Y",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["carrier_safety_basic_percentiles"].values()))
    assert stored["carrier_segment"] == "interstate_and_intrastate_hazmat_passenger"
    assert stored["unsafe_driving_percentile"] == 0.0
    assert stored["vehicle_maintenance_roadside_alert"] is True
    assert stored["vehicle_maintenance_basic_alert"] is True


def test_upsert_carrier_inspection_violations_preserves_feed_date_snapshots(
    fake_client: _FakeDirectPostgresDatabase,
):
    row = {
        "row_number": 1,
        "raw_values": [
            "726403509",
            "30-JAN-24",
            "1926619",
            "3922SLLS4",
            "Unsafe Driving",
            "false",
            "0",
            "10",
            "1",
            "10",
            "Failing to obey traffic control device",
            "Traffic Control",
            "D",
        ],
        "raw_fields": {
            "Unique_ID": "726403509",
            "Insp_Date": "30-JAN-24",
            "DOT_Number": "1926619",
            "Viol_Code": "3922SLLS4",
            "BASIC_Desc": "Unsafe Driving",
            "OOS_Indicator": "false",
            "OOS_Weight": "0",
            "Severity_Weight": "10",
            "Time_Weight": "1",
            "Total_Severity_Wght": "10",
            "Section_Desc": "Failing to obey traffic control device",
            "Group_Desc": "Traffic Control",
            "Viol_Unit": "D",
        },
    }

    upsert_carrier_inspection_violations(
        source_context=_source_context(
            feed_name="SMS Input - Violation",
            observed_at="2026-03-10T12:20:00Z",
            source_file_variant="csv_export",
        ),
        rows=[row],
    )
    upsert_carrier_inspection_violations(
        source_context=_source_context(
            feed_name="SMS Input - Violation",
            observed_at="2026-03-11T12:20:00Z",
            source_file_variant="csv_export",
        ),
        rows=[row],
    )

    assert len(fake_client.tables["carrier_inspection_violations"]) == 2
    stored_rows = list(fake_client.tables["carrier_inspection_violations"].values())
    assert {stored["feed_date"] for stored in stored_rows} == {"2026-03-10", "2026-03-11"}
    assert all(stored["inspection_date"] == "2024-01-30" for stored in stored_rows)


def test_upsert_carrier_inspection_violations_supports_vehicle_inspection_feed(
    fake_client: _FakeDirectPostgresDatabase,
):
    result = upsert_carrier_inspection_violations(
        source_context=_source_context(
            feed_name="Vehicle Inspections and Violations",
            observed_at="2026-03-10T12:21:00Z",
            source_file_variant="csv_export",
        ),
        rows=[
            {
                "row_number": 1,
                "raw_values": [
                    "20230504 2141",
                    "78529074",
                    "252617929",
                    "2",
                    "393",
                    "393.75A",
                    "1",
                    "194662753",
                    "12",
                    "Y",
                    "1",
                    "CIT-1",
                ],
                "raw_fields": {
                    "CHANGE_DATE": "20230504 2141",
                    "INSPECTION_ID": "78529074",
                    "INSP_VIOLATION_ID": "252617929",
                    "SEQ_NO": "2",
                    "PART_NO": "393",
                    "PART_NO_SECTION": "393.75A",
                    "INSP_VIOL_UNIT": "1",
                    "INSP_UNIT_ID": "194662753",
                    "INSP_VIOLATION_CATEGORY_ID": "12",
                    "OUT_OF_SERVICE_INDICATOR": "Y",
                    "DEFECT_VERIFICATION_ID": "1",
                    "CITATION_NUMBER": "CIT-1",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["carrier_inspection_violations"].values()))
    assert stored["inspection_unique_id"] == "78529074"
    assert stored["part_number"] == "393"
    assert stored["citation_number"] == "CIT-1"
    assert stored["oos_indicator"] is True


def test_upsert_carrier_inspections_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
    result = upsert_carrier_inspections(
        source_context=_source_context(
            feed_name="SMS Input - Inspection",
            observed_at="2026-03-10T12:30:00Z",
            source_file_variant="csv_export",
        ),
        rows=[
            {
                "row_number": 1,
                "raw_values": [
                    "726403509",
                    "1147001995",
                    "CT",
                    "1926619",
                    "30-JAN-24",
                    "3",
                    "CT",
                    "1",
                    "0",
                    "0",
                    "0",
                    "0",
                    "0",
                    "false",
                    "Truck Tractor",
                    "Freightliner",
                    "ABC123",
                    "CT",
                    "VINMAIN",
                    "DECAL1",
                    "Trailer",
                    "Utility",
                    "XYZ987",
                    "CT",
                    "VIN2",
                    "DECAL2",
                    "true",
                    "false",
                    "false",
                    "false",
                    "true",
                    "false",
                    "2",
                    "1",
                    "0",
                    "0",
                    "0",
                    "1",
                    "0",
                ],
                "raw_fields": {
                    "Unique_ID": "726403509",
                    "Report_Number": "1147001995",
                    "Report_State": "CT",
                    "DOT_Number": "1926619",
                    "Insp_Date": "30-JAN-24",
                    "Insp_level_ID": "3",
                    "County_code_State": "CT",
                    "Time_Weight": "1",
                    "Driver_OOS_Total": "0",
                    "Vehicle_OOS_Total": "0",
                    "Total_Hazmat_Sent": "0",
                    "OOS_Total": "0",
                    "Hazmat_OOS_Total": "0",
                    "Hazmat_Placard_req": "false",
                    "Unit_Type_Desc": "Truck Tractor",
                    "Unit_Make": "Freightliner",
                    "Unit_License": "ABC123",
                    "Unit_License_State": "CT",
                    "VIN": "VINMAIN",
                    "Unit_Decal_Number": "DECAL1",
                    "Unit_Type_Desc2": "Trailer",
                    "Unit_Make2": "Utility",
                    "Unit_License2": "XYZ987",
                    "Unit_License_State2": "CT",
                    "VIN2": "VIN2",
                    "Unit_Decal_Number2": "DECAL2",
                    "Unsafe_Insp": "true",
                    "Fatigued_Insp": "false",
                    "Dr_Fitness_Insp": "false",
                    "Subt_Alcohol_Insp": "false",
                    "Vh_Maint_Insp": "true",
                    "HM_Insp": "false",
                    "BASIC_Viol": "2",
                    "Unsafe_Viol": "1",
                    "Fatigued_Viol": "0",
                    "Dr_Fitness_Viol": "0",
                    "Subt_Alcohol_Viol": "0",
                    "Vh_Maint_Viol": "1",
                    "HM_Viol": "0",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["carrier_inspections"].values()))
    assert stored["inspection_unique_id"] == "726403509"
    assert stored["inspection_date"] == "2024-01-30"
    assert stored["unsafe_driving_inspection"] is True
    assert stored["vehicle_maintenance_violation_total"] == 1


def test_upsert_carrier_inspections_supports_vehicle_inspection_file_feed(
    fake_client: _FakeDirectPostgresDatabase,
):
    result = upsert_carrier_inspections(
        source_context=_source_context(
            feed_name="Vehicle Inspection File",
            observed_at="2026-03-10T13:00:00Z",
            source_file_variant="csv_export",
        ),
        rows=[
            {
                "row_number": 1,
                "raw_values": [
                    "20230327 2139",
                    "78058162",
                    "3129666",
                    "CT",
                    "3079001925",
                    "20230323",
                    "0920",
                    "0935",
                    "20230324",
                    "1",
                    "C",
                    "4",
                    "I-95 NORTHBOUND",
                    "CT",
                    "003",
                    "2",
                    "EA",
                    "5",
                    "R",
                    "",
                    "",
                    "",
                    "N",
                    "4.0",
                    "20230327 2000",
                    "N",
                    "N",
                    "0",
                    "N",
                    "N",
                    "N",
                    "Y",
                    "20230327 2139",
                    "N",
                    "80000",
                    "1",
                    "0",
                    "1",
                    "0",
                    "0",
                    "0",
                    "0",
                    "0",
                    "1111",
                    "A",
                    "20230327 2100",
                    "20230327 2105",
                    "0",
                    "3129666",
                    "M",
                    "20230327 2103",
                    "20230327 2050",
                    "CT001",
                    "20230327 2139",
                    "ACME HAULING",
                    "1 MAIN ST",
                    "HARTFORD",
                    "CT",
                    "06103",
                    "",
                    "MC123456",
                    "Y",
                    "STATE-1",
                ],
                "raw_fields": {
                    "CHANGE_DATE": "20230327 2139",
                    "INSPECTION_ID": "78058162",
                    "DOT_NUMBER": "3129666",
                    "REPORT_STATE": "CT",
                    "REPORT_NUMBER": "3079001925",
                    "INSP_DATE": "20230323",
                    "INSP_START_TIME": "0920",
                    "INSP_END_TIME": "0935",
                    "REGISTRATION_DATE": "20230324",
                    "REGION": "1",
                    "CI_STATUS_CODE": "C",
                    "LOCATION": "4",
                    "LOCATION_DESC": "I-95 NORTHBOUND",
                    "COUNTY_CODE_STATE": "CT",
                    "COUNTY_CODE": "003",
                    "INSP_LEVEL_ID": "2",
                    "SERVICE_CENTER": "EA",
                    "CENSUS_SOURCE_ID": "5",
                    "INSP_FACILITY": "R",
                    "SHIPPER_NAME": "",
                    "SHIPPING_PAPER_NUMBER": "",
                    "CARGO_TANK": "",
                    "HAZMAT_PLACARD_REQ": "N",
                    "SNET_VERSION_NUMBER": "4.0",
                    "SNET_SEARCH_DATE": "20230327 2000",
                    "ALCOHOL_CONTROL_SUB": "N",
                    "DRUG_INTRDCTN_SEARCH": "N",
                    "DRUG_INTRDCTN_ARRESTS": "0",
                    "SIZE_WEIGHT_ENF": "N",
                    "TRAFFIC_ENF": "N",
                    "LOCAL_ENF_JURISDICTION": "N",
                    "PEN_CEN_MATCH": "Y",
                    "FINAL_STATUS_DATE": "20230327 2139",
                    "POST_ACC_IND": "N",
                    "GROSS_COMB_VEH_WT": "80000",
                    "VIOL_TOTAL": "1",
                    "OOS_TOTAL": "0",
                    "DRIVER_VIOL_TOTAL": "1",
                    "DRIVER_OOS_TOTAL": "0",
                    "VEHICLE_VIOL_TOTAL": "0",
                    "VEHICLE_OOS_TOTAL": "0",
                    "HAZMAT_VIOL_TOTAL": "0",
                    "HAZMAT_OOS_TOTAL": "0",
                    "SNET_SEQUENCE_ID": "1111",
                    "TRANSACTION_CODE": "A",
                    "TRANSACTION_DATE": "20230327 2100",
                    "UPLOAD_DATE": "20230327 2105",
                    "UPLOAD_FIRST_BYTE": "0",
                    "UPLOAD_DOT_NUMBER": "3129666",
                    "UPLOAD_SEARCH_INDICATOR": "M",
                    "CENSUS_SEARCH_DATE": "20230327 2103",
                    "SNET_INPUT_DATE": "20230327 2050",
                    "SOURCE_OFFICE": "CT001",
                    "MCMIS_ADD_DATE": "20230327 2139",
                    "INSP_CARRIER_NAME": "ACME HAULING",
                    "INSP_CARRIER_STREET": "1 MAIN ST",
                    "INSP_CARRIER_CITY": "HARTFORD",
                    "INSP_CARRIER_STATE": "CT",
                    "INSP_CARRIER_ZIP_CODE": "06103",
                    "INSP_COLONIA": "",
                    "DOCKET_NUMBER": "MC123456",
                    "INSP_INTERSTATE": "Y",
                    "INSP_CARRIER_STATE_ID": "STATE-1",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["carrier_inspections"].values()))
    assert stored["inspection_unique_id"] == "78058162"
    assert stored["registration_date"] == "2023-03-24"
    assert stored["docket_number"] == "MC123456"
    assert stored["carrier_name"] == "ACME HAULING"


def test_upsert_motor_carrier_census_records_same_day_rerun_updates_same_feed_slot(
    fake_client: _FakeDirectPostgresDatabase,
):
    first_row = {
        "row_number": 1,
        "raw_values": [
            "1",
            "FEDERAL MOTOR CARRIER SAFETY ADMINISTRATION",
            "FMCSA TECHNOLOGY DIVISION",
            "C",
            "false",
            "false",
            "1200 NEW JERSEY AVENUE SE",
            "WASHINGTON",
            "DC",
            "20590",
            "US",
            "1200 NEW JERSEY AVENUE SE",
            "WASHINGTON",
            "DC",
            "20590",
            "US",
            "2023664000",
            "",
            "first@example.com",
            "01-JAN-24",
            "1000",
            "2023",
            "01-JAN-20",
            "DC",
            "5",
            "10",
            "2000",
            "2024",
            "1",
            "false",
            "true",
            "false",
            "false",
            "false",
            "false",
            "false",
            "false",
            "false",
            "false",
            "false",
            "false",
            "",
        ],
        "raw_fields": {
            "DOT_NUMBER": "1",
            "LEGAL_NAME": "FEDERAL MOTOR CARRIER SAFETY ADMINISTRATION",
            "DBA_NAME": "FMCSA TECHNOLOGY DIVISION",
            "CARRIER_OPERATION": "C",
            "HM_FLAG": "false",
            "PC_FLAG": "false",
            "PHY_STREET": "1200 NEW JERSEY AVENUE SE",
            "PHY_CITY": "WASHINGTON",
            "PHY_STATE": "DC",
            "PHY_ZIP": "20590",
            "PHY_COUNTRY": "US",
            "MAILING_STREET": "1200 NEW JERSEY AVENUE SE",
            "MAILING_CITY": "WASHINGTON",
            "MAILING_STATE": "DC",
            "MAILING_ZIP": "20590",
            "MAILING_COUNTRY": "US",
            "TELEPHONE": "2023664000",
            "FAX": "",
            "EMAIL_ADDRESS": "first@example.com",
            "MCS150_DATE": "01-JAN-24",
            "MCS150_MILEAGE": "1000",
            "MCS150_MILEAGE_YEAR": "2023",
            "ADD_DATE": "01-JAN-20",
            "OIC_STATE": "DC",
            "NBR_POWER_UNIT": "5",
            "DRIVER_TOTAL": "10",
            "RECENT_MILEAGE": "2000",
            "RECENT_MILEAGE_YEAR": "2024",
            "VMT_SOURCE_ID": "1",
            "PRIVATE_ONLY": "false",
            "AUTHORIZED_FOR_HIRE": "true",
            "EXEMPT_FOR_HIRE": "false",
            "PRIVATE_PROPERTY": "false",
            "PRIVATE_PASSENGER_BUSINESS": "false",
            "PRIVATE_PASSENGER_NONBUSINESS": "false",
            "MIGRANT": "false",
            "US_MAIL": "false",
            "FEDERAL_GOVERNMENT": "false",
            "STATE_GOVERNMENT": "false",
            "LOCAL_GOVERNMENT": "false",
            "INDIAN_TRIBE": "false",
            "OP_OTHER": "",
        },
    }
    second_row = {
        **first_row,
        "raw_values": [*first_row["raw_values"][:18], "second@example.com", *first_row["raw_values"][19:]],
        "raw_fields": {**first_row["raw_fields"], "EMAIL_ADDRESS": "second@example.com"},
    }

    upsert_motor_carrier_census_records(
        source_context=_source_context(
            feed_name="SMS Input - Motor Carrier Census",
            observed_at="2026-03-10T12:40:00Z",
            source_file_variant="csv_export",
        ),
        rows=[first_row],
    )
    upsert_motor_carrier_census_records(
        source_context=_source_context(
            feed_name="SMS Input - Motor Carrier Census",
            observed_at="2026-03-10T12:41:00Z",
            source_file_variant="csv_export",
        ),
        rows=[second_row],
    )

    assert len(fake_client.tables["motor_carrier_census_records"]) == 1
    stored = next(iter(fake_client.tables["motor_carrier_census_records"].values()))
    assert stored["feed_date"] == "2026-03-10"
    assert stored["email_address"] == "second@example.com"
    assert stored["authorized_for_hire"] is True


def test_upsert_motor_carrier_census_records_supports_company_census_file(
    fake_client: _FakeDirectPostgresDatabase,
):
    result = upsert_motor_carrier_census_records(
        source_context=_source_context(
            feed_name="Company Census File",
            observed_at="2026-03-10T12:45:00Z",
            source_file_variant="csv_export",
        ),
        rows=[
            {
                "row_number": 1,
                "raw_values": [],
                "raw_fields": {
                    "MCS150_DATE": "20240101",
                    "ADD_DATE": "20200115",
                    "STATUS_CODE": "A",
                    "DOT_NUMBER": "123456",
                    "DUN_BRADSTREET_NO": "123456789",
                    "PHY_OMC_REGION": "6",
                    "SAFETY_INV_TERR": "TX",
                    "CARRIER_OPERATION": "A",
                    "BUSINESS_ORG_ID": "3",
                    "MCS150_MILEAGE": "120000",
                    "MCS150_MILEAGE_YEAR": "2023",
                    "MCS151_MILEAGE": "115000",
                    "TOTAL_CARS": "0",
                    "MCS150_UPDATE_CODE_ID": "U",
                    "PRIOR_REVOKE_FLAG": "N",
                    "PRIOR_REVOKE_DOT_NUMBER": "",
                    "PHONE": "5125550100",
                    "FAX": "5125550101",
                    "CELL_PHONE": "5125550102",
                    "COMPANY_OFFICER_1": "JANE DOE",
                    "COMPANY_OFFICER_2": "JOHN DOE",
                    "BUSINESS_ORG_DESC": "Corporation",
                    "TRUCK_UNITS": "5",
                    "POWER_UNITS": "7",
                    "BUS_UNITS": "0",
                    "FLEETSIZE": "D",
                    "REVIEW_ID": "12345",
                    "RECORDABLE_CRASH_RATE": "1.250",
                    "MAIL_NATIONALITY_INDICATOR": "U",
                    "PHY_NATIONALITY_INDICATOR": "U",
                    "PHY_BARRIO": "",
                    "MAIL_BARRIO": "",
                    "CARSHIP": "C",
                    "DOCKET1PREFIX": "MC",
                    "DOCKET1": "654321",
                    "DOCKET2PREFIX": "",
                    "DOCKET2": "",
                    "DOCKET3PREFIX": "",
                    "DOCKET3": "",
                    "POINTNUM": "P",
                    "TOTAL_INTRASTATE_DRIVERS": "0",
                    "MCSIPSTEP": "2",
                    "MCSIPDATE": "20240201",
                    "HM_Ind": "Y",
                    "INTERSTATE_BEYOND_100_MILES": "4",
                    "INTERSTATE_WITHIN_100_MILES": "2",
                    "INTRASTATE_BEYOND_100_MILES": "0",
                    "INTRASTATE_WITHIN_100_MILES": "0",
                    "TOTAL_CDL": "6",
                    "TOTAL_DRIVERS": "6",
                    "AVG_DRIVERS_LEASED_PER_MONTH": "1",
                    "CLASSDEF": "AUTHORIZED FOR HIRE;OTHER-FARMER",
                    "LEGAL_NAME": "ACME LOGISTICS LLC",
                    "DBA_NAME": "ACME LOGISTICS",
                    "PHY_STREET": "1 MAIN ST",
                    "PHY_CITY": "AUSTIN",
                    "PHY_COUNTRY": "US",
                    "PHY_STATE": "TX",
                    "PHY_ZIP": "78701",
                    "PHY_CNTY": "453",
                    "CARRIER_MAILING_STREET": "PO BOX 1",
                    "CARRIER_MAILING_STATE": "TX",
                    "CARRIER_MAILING_CITY": "AUSTIN",
                    "CARRIER_MAILING_COUNTRY": "US",
                    "CARRIER_MAILING_ZIP": "78702",
                    "CARRIER_MAILING_CNTY": "453",
                    "CARRIER_MAILING_UND_DATE": "",
                    "DRIVER_INTER_TOTAL": "6",
                    "EMAIL_ADDRESS": "ops@acme.com",
                    "REVIEW_TYPE": "C",
                    "REVIEW_DATE": "20240215",
                    "SAFETY_RATING": "S",
                    "SAFETY_RATING_DATE": "20240220",
                    "UNDELIV_PHY": "",
                    "CRGO_GENFREIGHT": "X",
                    "CRGO_HOUSEHOLD": "",
                    "CRGO_METALSHEET": "",
                    "CRGO_MOTOVEH": "",
                    "CRGO_DRIVETOW": "",
                    "CRGO_LOGPOLE": "",
                    "CRGO_BLDGMAT": "",
                    "CRGO_MOBILEHOME": "",
                    "CRGO_MACHLRG": "",
                    "CRGO_PRODUCE": "",
                    "CRGO_LIQGAS": "",
                    "CRGO_INTERMODAL": "",
                    "CRGO_PASSENGERS": "",
                    "CRGO_OILFIELD": "",
                    "CRGO_LIVESTOCK": "",
                    "CRGO_GRAINFEED": "",
                    "CRGO_COALCOKE": "",
                    "CRGO_MEAT": "",
                    "CRGO_GARBAGE": "",
                    "CRGO_USMAIL": "",
                    "CRGO_CHEM": "",
                    "CRGO_DRYBULK": "",
                    "CRGO_COLDFOOD": "",
                    "CRGO_BEVERAGES": "",
                    "CRGO_PAPERPROD": "",
                    "CRGO_UTILITY": "",
                    "CRGO_FARMSUPP": "",
                    "CRGO_CONSTRUCT": "",
                    "CRGO_WATERWELL": "",
                    "CRGO_CARGOOTHR": "X",
                    "CRGO_CARGOOTHR_DESC": "OTHER-FARMER",
                    "OWNTRUCK": "2",
                    "OWNTRACT": "3",
                    "OWNTRAIL": "4",
                    "OWNCOACH": "0",
                    "OWNSCHOOL_1_8": "0",
                    "OWNSCHOOL_9_15": "0",
                    "OWNSCHOOL_16": "0",
                    "OWNBUS_16": "0",
                    "OWNVAN_1_8": "0",
                    "OWNVAN_9_15": "0",
                    "OWNLIMO_1_8": "0",
                    "OWNLIMO_9_15": "0",
                    "OWNLIMO_16": "0",
                    "TRMTRUCK": "0",
                    "TRMTRACT": "0",
                    "TRMTRAIL": "0",
                    "TRMCOACH": "0",
                    "TRMSCHOOL_1_8": "0",
                    "TRMSCHOOL_9_15": "0",
                    "TRMSCHOOL_16": "0",
                    "TRMBUS_16": "0",
                    "TRMVAN_1_8": "0",
                    "TRMVAN_9_15": "0",
                    "TRMLIMO_1_8": "0",
                    "TRMLIMO_9_15": "0",
                    "TRMLIMO_16": "0",
                    "TRPTRUCK": "0",
                    "TRPTRACT": "0",
                    "TRPTRAIL": "0",
                    "TRPCOACH": "0",
                    "TRPSCHOOL_1_8": "0",
                    "TRPSCHOOL_9_15": "0",
                    "TRPSCHOOL_16": "0",
                    "TRPBUS_16": "0",
                    "TRPVAN_1_8": "0",
                    "TRPVAN_9_15": "0",
                    "TRPLIMO_1_8": "0",
                    "TRPLIMO_9_15": "0",
                    "TRPLIMO_16": "0",
                    "DOCKET1_STATUS_CODE": "A",
                    "DOCKET2_STATUS_CODE": "",
                    "DOCKET3_STATUS_CODE": "",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["motor_carrier_census_records"].values()))
    assert stored["status_code"] == "A"
    assert stored["mcs150_date"] == "2024-01-01"
    assert stored["authorized_for_hire"] is True
    assert stored["other_operation_description"] == "OTHER-FARMER"
    assert stored["cargo_general_freight"] is True


def test_shared_table_keeps_daily_and_all_history_rows_separate_on_same_feed_date(
    fake_client: _FakeDirectPostgresDatabase,
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


def test_upsert_vehicle_inspection_units_preserves_multiple_rows_for_same_inspection(
    fake_client: _FakeDirectPostgresDatabase,
):
    row_one = {
        "row_number": 1,
        "raw_values": ["20230501 1045", "78487801", "194662753", "9", "1", "UTILITY", "A1", "ABC123", "TX", "VIN1", "Y", "D1"],
        "raw_fields": {
            "CHANGE_DATE": "20230501 1045",
            "INSPECTION_ID": "78487801",
            "INSP_UNIT_ID": "194662753",
            "INSP_UNIT_TYPE_ID": "9",
            "INSP_UNIT_NUMBER": "1",
            "INSP_UNIT_MAKE": "UTILITY",
            "INSP_UNIT_COMPANY": "A1",
            "INSP_UNIT_LICENSE": "ABC123",
            "INSP_UNIT_LICENSE_STATE": "TX",
            "INSP_UNIT_VEHICLE_ID_NUMBER": "VIN1",
            "INSP_UNIT_DECAL": "Y",
            "INSP_UNIT_DECAL_NUMBER": "D1",
        },
    }
    row_two = {
        **row_one,
        "row_number": 2,
        "raw_values": ["20230501 1045", "78487801", "194662754", "11", "2", "FREIGHTLINER", "A2", "XYZ987", "TX", "VIN2", "N", "D2"],
        "raw_fields": {**row_one["raw_fields"], "INSP_UNIT_ID": "194662754", "INSP_UNIT_NUMBER": "2", "INSP_UNIT_MAKE": "FREIGHTLINER", "INSP_UNIT_COMPANY": "A2", "INSP_UNIT_LICENSE": "XYZ987", "INSP_UNIT_VEHICLE_ID_NUMBER": "VIN2", "INSP_UNIT_DECAL": "N", "INSP_UNIT_DECAL_NUMBER": "D2"},
    }

    upsert_vehicle_inspection_units(
        source_context=_source_context(feed_name="Inspections Per Unit", observed_at="2026-03-10T12:50:00Z", source_file_variant="csv_export"),
        rows=[row_one, row_two],
    )

    assert len(fake_client.tables["vehicle_inspection_units"]) == 2


def test_upsert_vehicle_inspection_special_studies_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
    result = upsert_vehicle_inspection_special_studies(
        source_context=_source_context(feed_name="Special Studies", observed_at="2026-03-10T12:55:00Z", source_file_variant="csv_export"),
        rows=[
            {
                "row_number": 1,
                "raw_values": ["20230518 2144", "78668161", "16892759", "MORGAN LEWIS", "4"],
                "raw_fields": {
                    "CHANGE_DATE": "20230518 2144",
                    "INSPECTION_ID": "78668161",
                    "INSP_STUDY_ID": "16892759",
                    "STUDY": "MORGAN LEWIS",
                    "SEQ_NO": "4",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["vehicle_inspection_special_studies"].values()))
    assert stored["inspection_study_id"] == "16892759"
    assert stored["sequence_number"] == 4


def test_upsert_vehicle_inspection_citations_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
    result = upsert_vehicle_inspection_citations(
        source_context=_source_context(feed_name="Inspections and Citations", observed_at="2026-03-10T12:56:00Z", source_file_variant="csv_export"),
        rows=[
            {
                "row_number": 1,
                "raw_values": ["20240220 2141", "78058442", "2", "1", "3", "Paid"],
                "raw_fields": {
                    "CHANGE_DATE": "20240220 2141",
                    "INSPECTION_ID": "78058442",
                    "VIOSEQNUM": "2",
                    "ADJSEQ": "1",
                    "CITATION_CODE": "3",
                    "CITATION_RESULT": "Paid",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["vehicle_inspection_citations"].values()))
    assert stored["inspection_id"] == "78058442"
    assert stored["citation_result"] == "Paid"


def test_upsert_out_of_service_orders_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
    result = upsert_out_of_service_orders(
        source_context=_source_context(feed_name="OUT OF SERVICE ORDERS", observed_at="2026-03-10T13:05:00Z", source_file_variant="csv_export"),
        rows=[
            {
                "row_number": 1,
                "raw_values": ["1438", "AUSTIN URETHANE INC", "", "2022-07-09", "Unsatisfactory = Unfit", "ACTIVE", "2022-08-01"],
                "raw_fields": {
                    "DOT_NUMBER": "1438",
                    "LEGAL_NAME": "AUSTIN URETHANE INC",
                    "DBA_NAME": "",
                    "OOS_DATE": "2022-07-09",
                    "OOS_REASON": "Unsatisfactory = Unfit",
                    "STATUS": "ACTIVE",
                    "OOS_RESCIND_DATE": "2022-08-01",
                },
            }
        ],
    )

    assert result["rows_written"] == 1
    stored = next(iter(fake_client.tables["out_of_service_orders"].values()))
    assert stored["oos_date"] == "2022-07-09"
    assert stored["oos_rescind_date"] == "2022-08-01"


def test_upsert_insurance_filing_rejections_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
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


def test_upsert_operating_authority_histories_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
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
    fake_client: _FakeDirectPostgresDatabase,
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
    fake_client: _FakeDirectPostgresDatabase,
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
    first_stored = next(iter(fake_client.tables["operating_authority_revocations"].values()))
    upsert_operating_authority_revocations(
        source_context=_source_context(feed_name="Revocation", observed_at="2026-03-10T15:06:00Z"),
        rows=[second_row],
    )

    assert len(fake_client.tables["operating_authority_revocations"]) == 1
    stored = next(iter(fake_client.tables["operating_authority_revocations"].values()))
    assert stored["feed_date"] == "2026-03-10"
    assert stored["row_position"] == 1
    assert stored["revocation_type"] == "Safety"
    assert stored["record_fingerprint"] == first_stored["record_fingerprint"]
    assert stored["first_observed_at"] == "2026-03-10T15:05:00Z"
    assert stored["last_observed_at"] == "2026-03-10T15:06:00Z"
    assert stored["created_at"] == first_stored["created_at"]


def test_upsert_insurance_policies_preserves_blank_row_removal_signal(
    fake_client: _FakeDirectPostgresDatabase,
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


def test_upsert_insurance_policy_filings_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
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


def test_upsert_insurance_policy_history_events_persists_typed_row(fake_client: _FakeDirectPostgresDatabase):
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


def test_direct_postgres_failures_surface_without_fake_success(
    monkeypatch: pytest.MonkeyPatch,
):
    class _FailingCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query: str, params: tuple[str, str]):
            return self

        def fetchall(self):
            return []

        def executemany(self, query: str, params_seq: list[dict]):
            raise RuntimeError("direct postgres write failed")

    class _FailingConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def cursor(self):
            return _FailingCursor()

    monkeypatch.setattr(
        fmcsa_daily_diff_common,
        "get_fmcsa_direct_postgres_connection",
        lambda: _FailingConnection(),
    )

    with pytest.raises(RuntimeError, match="direct postgres write failed"):
        upsert_process_agent_filings(
            source_context=_source_context(feed_name="BOC3", observed_at="2026-03-10T15:05:00Z"),
            rows=[
                {
                    "row_number": 1,
                    "raw_values": [
                        "MC555555",
                        "55556666",
                        "AGENT ONE",
                        "LEGAL",
                        "1 MAIN",
                        "AUSTIN",
                        "TX",
                        "USA",
                        "78701",
                    ],
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
            ],
        )


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
