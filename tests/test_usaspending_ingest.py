# tests/test_usaspending_ingest.py — USASpending.gov ingest pipeline tests

from __future__ import annotations

import csv
import io
import os
import re
import tempfile
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.usaspending_column_map import (
    USASPENDING_COLUMN_COUNT,
    USASPENDING_COLUMNS,
    USASPENDING_CSV_TO_DB_MAP,
    USASPENDING_DB_COLUMN_NAMES,
    USASPENDING_DELTA_COLUMN_COUNT,
    USASPENDING_DELTA_EXTRA_COLUMNS,
)
from app.services.usaspending_common import (
    UsaspendingSourceContext,
    build_usaspending_contract_row,
    parse_usaspending_csv_row,
)


# ── Column Map Tests ──────────────────────────────────────────────────────


class TestUsaspendingColumnMap:
    def test_column_count(self):
        assert USASPENDING_COLUMN_COUNT == 297

    def test_delta_column_count(self):
        assert USASPENDING_DELTA_COLUMN_COUNT == 299

    def test_first_column(self):
        assert USASPENDING_COLUMNS[0]["db_column_name"] == "contract_transaction_unique_key"
        assert USASPENDING_COLUMNS[0]["csv_header_name"] == "contract_transaction_unique_key"
        assert USASPENDING_COLUMNS[0]["position"] == 1

    def test_last_column(self):
        assert USASPENDING_COLUMNS[-1]["db_column_name"] == "last_modified_date"
        assert USASPENDING_COLUMNS[-1]["csv_header_name"] == "last_modified_date"
        assert USASPENDING_COLUMNS[-1]["position"] == 297

    def test_recipient_uei_present(self):
        col49 = USASPENDING_COLUMNS[48]  # position 49, zero-indexed 48
        assert col49["db_column_name"] == "recipient_uei"
        assert col49["position"] == 49

    def test_naics_code_present(self):
        col110 = USASPENDING_COLUMNS[109]  # position 110, zero-indexed 109
        assert col110["db_column_name"] == "naics_code"
        assert col110["position"] == 110

    def test_all_db_column_names_valid_postgres(self):
        pattern = re.compile(r"^[a-z_][a-z0-9_]*$")
        for col in USASPENDING_COLUMNS:
            assert pattern.fullmatch(col["db_column_name"]), (
                f"Invalid Postgres identifier: {col['db_column_name']} (position {col['position']})"
            )

    def test_no_duplicate_db_column_names(self):
        assert len(set(USASPENDING_DB_COLUMN_NAMES)) == 297

    def test_no_hyphens_in_db_column_names(self):
        for name in USASPENDING_DB_COLUMN_NAMES:
            assert "-" not in name, f"Hyphen found in db_column_name: {name}"

    def test_digit_prefixed_columns_have_col_prefix(self):
        digit_cols = [c for c in USASPENDING_COLUMNS if c["csv_header_name"][0].isdigit()]
        assert len(digit_cols) == 3  # 1862, 1890, 1994
        for c in digit_cols:
            assert c["db_column_name"].startswith("col_"), (
                f"Digit-prefixed column missing col_ prefix: {c['csv_header_name']}"
            )

    def test_csv_to_db_map_covers_all_columns(self):
        assert len(USASPENDING_CSV_TO_DB_MAP) == 297

    def test_delta_extra_columns(self):
        assert len(USASPENDING_DELTA_EXTRA_COLUMNS) == 2
        names = [c["db_column_name"] for c in USASPENDING_DELTA_EXTRA_COLUMNS]
        assert "correction_delete_ind" in names
        assert "agency_id" in names

    def test_db_column_names_list_matches(self):
        assert USASPENDING_DB_COLUMN_NAMES == [c["db_column_name"] for c in USASPENDING_COLUMNS]


# ── CSV Parser Tests ──────────────────────────────────────────────────────


def _make_full_row_dict(txn_key: str = "TEST_TXN_KEY") -> dict[str, str]:
    """Build a 297-column row dict with a given transaction key."""
    row = {}
    for col in USASPENDING_COLUMNS:
        row[col["csv_header_name"]] = ""
    row["contract_transaction_unique_key"] = txn_key
    row["recipient_uei"] = "TESTUE123456"
    row["recipient_name"] = "TEST CORP"
    row["naics_code"] = "541519"
    return row


def _make_delta_row_dict(txn_key: str = "TEST_TXN_KEY") -> dict[str, str]:
    """Build a 299-column delta row dict."""
    row = _make_full_row_dict(txn_key)
    row["correction_delete_ind"] = ""
    row["agency_id"] = "0300"
    return row


class TestUsaspendingCsvParser:
    def test_valid_full_row_parses(self):
        row_dict = _make_full_row_dict("ABC_123")
        result = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert result is not None
        assert result["row_number"] == 1
        assert result["fields"]["contract_transaction_unique_key"] == "ABC_123"

    def test_valid_delta_row_parses(self):
        row_dict = _make_delta_row_dict("DELTA_123")
        result = parse_usaspending_csv_row(row_dict, 5, is_delta=True)
        assert result is not None
        assert result["row_number"] == 5
        assert result["fields"]["agency_id"] == "0300"

    def test_missing_txn_key_returns_none(self):
        row_dict = _make_full_row_dict("")
        result = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert result is None

    def test_whitespace_txn_key_returns_none(self):
        row_dict = _make_full_row_dict("   ")
        result = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert result is None

    def test_wrong_column_count_returns_none(self):
        row_dict = _make_full_row_dict("ABC")
        row_dict["extra_col"] = "surprise"  # 298 columns now
        result = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert result is None

    def test_delta_row_with_full_count_fails(self):
        """A 297-column row should fail when is_delta=True (expects 299)."""
        row_dict = _make_full_row_dict("ABC")
        result = parse_usaspending_csv_row(row_dict, 1, is_delta=True)
        assert result is None


# ── Row Builder Tests ─────────────────────────────────────────────────────


class TestUsaspendingRowBuilder:
    SOURCE_CONTEXT = UsaspendingSourceContext(
        extract_date="2026-03-07",
        extract_type="FULL",
        source_filename="FY2026_All_Contracts_Full_20260307_1.csv",
    )

    def test_csv_headers_map_to_db_names(self):
        row_dict = _make_full_row_dict("TXN_001")
        row_dict["naics_code"] = "236220"
        parsed = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, self.SOURCE_CONTEXT)
        assert built["contract_transaction_unique_key"] == "TXN_001"
        assert built["naics_code"] == "236220"
        assert built["recipient_uei"] == "TESTUE123456"

    def test_extract_metadata_populated(self):
        row_dict = _make_full_row_dict("TXN_002")
        parsed = parse_usaspending_csv_row(row_dict, 42, is_delta=False)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, self.SOURCE_CONTEXT)
        assert built["extract_date"] == "2026-03-07"
        assert built["extract_type"] == "FULL"
        assert built["source_filename"] == "FY2026_All_Contracts_Full_20260307_1.csv"
        assert built["source_provider"] == "usaspending"
        assert built["row_position"] == 42

    def test_delta_columns_populated_for_delta(self):
        delta_ctx = UsaspendingSourceContext(
            extract_date="2026-03-08",
            extract_type="DELTA",
            source_filename="FY(All)_All_Contracts_Delta_20260308_1.csv",
        )
        row_dict = _make_delta_row_dict("TXN_DELTA")
        row_dict["correction_delete_ind"] = "C"
        row_dict["agency_id"] = "0300"
        parsed = parse_usaspending_csv_row(row_dict, 1, is_delta=True)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, delta_ctx, is_delta=True)
        assert built["correction_delete_ind"] == "C"
        assert built["agency_id"] == "0300"

    def test_delta_columns_none_for_full(self):
        row_dict = _make_full_row_dict("TXN_FULL")
        parsed = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, self.SOURCE_CONTEXT)
        assert built["correction_delete_ind"] is None
        assert built["agency_id"] is None

    def test_empty_strings_become_none(self):
        row_dict = _make_full_row_dict("TXN_003")
        row_dict["recipient_duns"] = ""
        row_dict["recipient_doing_business_as_name"] = "   "
        parsed = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, self.SOURCE_CONTEXT)
        assert built["recipient_duns"] is None
        assert built["recipient_doing_business_as_name"] is None

    def test_hyphenated_csv_name_maps_correctly(self):
        """COVID-19 column (hyphen in CSV name) should map to underscore db name."""
        row_dict = _make_full_row_dict("TXN_004")
        row_dict["outlayed_amount_from_COVID-19_supplementals_for_overall_award"] = "1234.56"
        parsed = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, self.SOURCE_CONTEXT)
        assert built["outlayed_amount_from_covid_19_supplementals_for_overall_award"] == "1234.56"

    def test_digit_prefixed_csv_name_maps_correctly(self):
        """1862_land_grant_college should map to col_1862_land_grant_college."""
        row_dict = _make_full_row_dict("TXN_005")
        row_dict["1862_land_grant_college"] = "t"
        parsed = parse_usaspending_csv_row(row_dict, 1, is_delta=False)
        assert parsed is not None

        built = build_usaspending_contract_row(parsed, self.SOURCE_CONTEXT)
        assert built["col_1862_land_grant_college"] == "t"


# ── Ingest Service Tests (Mock DB) ───────────────────────────────────────


def _write_csv_to_tempfile(header: list[str], rows: list[list[str]]) -> str:
    """Write a CSV to a temp file and return the path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    writer = csv.writer(tmp)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    tmp.close()
    return tmp.name


def _make_csv_header() -> list[str]:
    return [c["csv_header_name"] for c in USASPENDING_COLUMNS]


def _make_csv_data_row(txn_key: str) -> list[str]:
    row = [""] * USASPENDING_COLUMN_COUNT
    row[0] = txn_key  # contract_transaction_unique_key
    row[48] = "TESTUE123456"  # recipient_uei
    row[50] = "TEST CORP"  # recipient_name
    return row


class TestUsaspendingIngestService:
    @patch("app.services.usaspending_extract_ingest.upsert_usaspending_contracts")
    def test_single_csv_ingest(self, mock_upsert: MagicMock):
        from app.services.usaspending_extract_ingest import ingest_usaspending_csv

        mock_upsert.return_value = {"rows_written": 3}

        header = _make_csv_header()
        rows = [_make_csv_data_row(f"TXN_{i}") for i in range(3)]
        csv_path = _write_csv_to_tempfile(header, rows)

        try:
            result = ingest_usaspending_csv(
                csv_file_path=csv_path,
                extract_date="2026-03-07",
                extract_type="FULL",
                source_filename="test.csv",
                chunk_size=50_000,
            )
            assert result["total_rows_parsed"] == 3
            assert result["total_rows_accepted"] == 3
            assert result["total_rows_rejected"] == 0
            assert mock_upsert.call_count == 1
        finally:
            os.unlink(csv_path)

    @patch("app.services.usaspending_extract_ingest.upsert_usaspending_contracts")
    def test_chunking_behavior(self, mock_upsert: MagicMock):
        from app.services.usaspending_extract_ingest import ingest_usaspending_csv

        mock_upsert.return_value = {"rows_written": 2}

        header = _make_csv_header()
        rows = [_make_csv_data_row(f"TXN_{i}") for i in range(5)]
        csv_path = _write_csv_to_tempfile(header, rows)

        try:
            result = ingest_usaspending_csv(
                csv_file_path=csv_path,
                extract_date="2026-03-07",
                extract_type="FULL",
                source_filename="test.csv",
                chunk_size=2,  # Force 3 chunks: 2+2+1
            )
            assert result["total_rows_parsed"] == 5
            assert result["chunks_processed"] == 3
            assert mock_upsert.call_count == 3
        finally:
            os.unlink(csv_path)

    @patch("app.services.usaspending_extract_ingest.upsert_usaspending_contracts")
    def test_error_propagation(self, mock_upsert: MagicMock):
        from app.services.usaspending_extract_ingest import ingest_usaspending_csv

        mock_upsert.side_effect = RuntimeError("DB down")

        header = _make_csv_header()
        rows = [_make_csv_data_row("TXN_1")]
        csv_path = _write_csv_to_tempfile(header, rows)

        try:
            with pytest.raises(RuntimeError, match="USASpending ingest failed"):
                ingest_usaspending_csv(
                    csv_file_path=csv_path,
                    extract_date="2026-03-07",
                    extract_type="FULL",
                    source_filename="test.csv",
                )
        finally:
            os.unlink(csv_path)

    @patch("app.services.usaspending_extract_ingest.ingest_usaspending_csv")
    def test_zip_ingest_calls_csv_per_file(self, mock_csv_ingest: MagicMock):
        from app.services.usaspending_extract_ingest import ingest_usaspending_zip

        mock_csv_ingest.return_value = {
            "source_filename": "test.csv",
            "total_rows_parsed": 100,
            "total_rows_accepted": 100,
            "total_rows_rejected": 0,
            "total_rows_written": 100,
            "chunks_processed": 1,
            "total_elapsed_ms": 50.0,
        }

        # Create a ZIP with 2 CSVs
        header = _make_csv_header()
        zip_path = tempfile.mktemp(suffix=".zip")
        try:
            with zipfile.ZipFile(zip_path, "w") as zf:
                for name in ["file_1.csv", "file_2.csv"]:
                    buf = io.StringIO()
                    writer = csv.writer(buf)
                    writer.writerow(header)
                    writer.writerow(_make_csv_data_row("TXN_1"))
                    zf.writestr(name, buf.getvalue())

            result = ingest_usaspending_zip(
                zip_file_path=zip_path,
                extract_date="2026-03-07",
                extract_type="FULL",
            )
            assert result["csv_files_processed"] == 2
            assert mock_csv_ingest.call_count == 2
            assert result["total_rows_parsed"] == 200
        finally:
            os.unlink(zip_path)
