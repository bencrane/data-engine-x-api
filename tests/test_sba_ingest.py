# tests/test_sba_ingest.py — SBA 7(a) loan ingest pipeline tests

from __future__ import annotations

import csv
import os
import re
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from app.services.sba_column_map import (
    SBA_COLUMN_COUNT,
    SBA_COLUMNS,
    SBA_CSV_TO_DB_MAP,
    SBA_DB_COLUMN_NAMES,
)
from app.services.sba_common import (
    SbaSourceContext,
    build_sba_loan_row,
    parse_sba_csv_row,
)


# ── Column Map Tests ──────────────────────────────────────────────────────


class TestSbaColumnMap:
    def test_column_count(self):
        assert SBA_COLUMN_COUNT == 43

    def test_first_column(self):
        assert SBA_COLUMNS[0]["db_column_name"] == "asofdate"
        assert SBA_COLUMNS[0]["csv_header_name"] == "asofdate"
        assert SBA_COLUMNS[0]["position"] == 1

    def test_last_column(self):
        assert SBA_COLUMNS[-1]["db_column_name"] == "soldsecmrktind"
        assert SBA_COLUMNS[-1]["csv_header_name"] == "soldsecmrktind"
        assert SBA_COLUMNS[-1]["position"] == 43

    def test_key_columns_present(self):
        names = {c["db_column_name"] for c in SBA_COLUMNS}
        for key_col in ["borrname", "naicscode", "grossapproval", "approvaldate", "borrstate", "loanstatus"]:
            assert key_col in names, f"Key column missing: {key_col}"

    def test_all_db_column_names_valid_postgres(self):
        pattern = re.compile(r"^[a-z_][a-z0-9_]*$")
        for col in SBA_COLUMNS:
            assert pattern.fullmatch(col["db_column_name"]), (
                f"Invalid Postgres identifier: {col['db_column_name']} (position {col['position']})"
            )

    def test_no_duplicate_db_column_names(self):
        assert len(set(SBA_DB_COLUMN_NAMES)) == 43

    def test_csv_to_db_map_covers_all_columns(self):
        assert len(SBA_CSV_TO_DB_MAP) == 43

    def test_db_column_names_list_matches(self):
        assert SBA_DB_COLUMN_NAMES == [c["db_column_name"] for c in SBA_COLUMNS]


# ── CSV Parser Tests ──────────────────────────────────────────────────────


def _make_sba_row_dict(borrname: str = "TEST CORP") -> dict[str, str]:
    """Build a 43-column row dict with a given borrower name."""
    row = {}
    for col in SBA_COLUMNS:
        row[col["csv_header_name"]] = ""
    row["borrname"] = borrname
    row["borrstreet"] = "123 MAIN ST"
    row["borrcity"] = "DALLAS"
    row["borrstate"] = "TX"
    row["borrzip"] = "75201"
    row["naicscode"] = "332710"
    row["grossapproval"] = "350000"
    row["approvaldate"] = "07/18/2025"
    row["asofdate"] = "09/30/2025"
    row["loanstatus"] = "EXEMPT"
    return row


class TestSbaCsvParser:
    def test_valid_row_parses(self):
        row_dict = _make_sba_row_dict("ACME INC")
        result = parse_sba_csv_row(row_dict, 1)
        assert result is not None
        assert result["row_number"] == 1
        assert result["fields"]["borrname"] == "ACME INC"

    def test_missing_borrname_returns_none(self):
        row_dict = _make_sba_row_dict("")
        result = parse_sba_csv_row(row_dict, 1)
        assert result is None

    def test_whitespace_borrname_returns_none(self):
        row_dict = _make_sba_row_dict("   ")
        result = parse_sba_csv_row(row_dict, 1)
        assert result is None

    def test_wrong_column_count_returns_none(self):
        row_dict = _make_sba_row_dict("ACME INC")
        row_dict["extra_col"] = "surprise"  # 44 columns now
        result = parse_sba_csv_row(row_dict, 1)
        assert result is None


# ── Row Builder Tests ─────────────────────────────────────────────────────


class TestSbaRowBuilder:
    SOURCE_CONTEXT = SbaSourceContext(
        extract_date="2025-09-30",
        source_filename="foia-7a-fy2020-present-asof-250930.csv",
        source_url="https://data.sba.gov/example",
    )

    def test_csv_headers_map_to_db_names(self):
        row_dict = _make_sba_row_dict("ACME INC")
        parsed = parse_sba_csv_row(row_dict, 1)
        assert parsed is not None

        built = build_sba_loan_row(parsed, self.SOURCE_CONTEXT)
        assert built["borrname"] == "ACME INC"
        assert built["naicscode"] == "332710"
        assert built["grossapproval"] == "350000"

    def test_extract_metadata_populated(self):
        row_dict = _make_sba_row_dict("ACME INC")
        parsed = parse_sba_csv_row(row_dict, 42)
        assert parsed is not None

        built = build_sba_loan_row(parsed, self.SOURCE_CONTEXT)
        assert built["extract_date"] == "2025-09-30"
        assert built["source_filename"] == "foia-7a-fy2020-present-asof-250930.csv"
        assert built["source_url"] == "https://data.sba.gov/example"
        assert built["source_provider"] == "sba"
        assert built["row_position"] == 42

    def test_empty_strings_become_none(self):
        row_dict = _make_sba_row_dict("ACME INC")
        row_dict["franchisename"] = ""
        row_dict["chargeoffdate"] = "   "
        parsed = parse_sba_csv_row(row_dict, 1)
        assert parsed is not None

        built = build_sba_loan_row(parsed, self.SOURCE_CONTEXT)
        assert built["franchisename"] is None
        assert built["chargeoffdate"] is None

    def test_whitespace_stripped(self):
        row_dict = _make_sba_row_dict("  ACME INC  ")
        parsed = parse_sba_csv_row(row_dict, 1)
        assert parsed is not None

        built = build_sba_loan_row(parsed, self.SOURCE_CONTEXT)
        assert built["borrname"] == "ACME INC"


# ── Ingest Service Tests (Mock DB) ───────────────────────────────────────


def _write_sba_csv_to_tempfile(header: list[str], rows: list[list[str]]) -> str:
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


def _make_sba_csv_header() -> list[str]:
    return [c["csv_header_name"] for c in SBA_COLUMNS]


def _make_sba_csv_data_row(borrname: str) -> list[str]:
    row = [""] * SBA_COLUMN_COUNT
    row[0] = "09/30/2025"   # asofdate
    row[3] = borrname        # borrname
    row[4] = "123 MAIN ST"  # borrstreet
    row[5] = "DALLAS"       # borrcity
    row[6] = "TX"           # borrstate
    row[15] = "350000"      # grossapproval
    row[17] = "07/18/2025"  # approvaldate
    row[25] = "332710"      # naicscode
    return row


class TestSbaIngestService:
    @patch("app.services.sba_ingest.upsert_sba_loans")
    def test_single_csv_ingest(self, mock_upsert: MagicMock):
        from app.services.sba_ingest import ingest_sba_csv

        mock_upsert.return_value = {"rows_written": 3}

        header = _make_sba_csv_header()
        rows = [_make_sba_csv_data_row(f"CORP_{i}") for i in range(3)]
        csv_path = _write_sba_csv_to_tempfile(header, rows)

        try:
            result = ingest_sba_csv(
                csv_file_path=csv_path,
                extract_date="2025-09-30",
                source_filename="test.csv",
                chunk_size=50_000,
            )
            assert result["total_rows_parsed"] == 3
            assert result["total_rows_accepted"] == 3
            assert result["total_rows_rejected"] == 0
            assert mock_upsert.call_count == 1
        finally:
            os.unlink(csv_path)

    @patch("app.services.sba_ingest.upsert_sba_loans")
    def test_chunking_behavior(self, mock_upsert: MagicMock):
        from app.services.sba_ingest import ingest_sba_csv

        mock_upsert.return_value = {"rows_written": 2}

        header = _make_sba_csv_header()
        rows = [_make_sba_csv_data_row(f"CORP_{i}") for i in range(5)]
        csv_path = _write_sba_csv_to_tempfile(header, rows)

        try:
            result = ingest_sba_csv(
                csv_file_path=csv_path,
                extract_date="2025-09-30",
                source_filename="test.csv",
                chunk_size=2,  # Force 3 chunks: 2+2+1
            )
            assert result["total_rows_parsed"] == 5
            assert result["chunks_processed"] == 3
            assert mock_upsert.call_count == 3
        finally:
            os.unlink(csv_path)

    @patch("app.services.sba_ingest.upsert_sba_loans")
    def test_error_propagation(self, mock_upsert: MagicMock):
        from app.services.sba_ingest import ingest_sba_csv

        mock_upsert.side_effect = RuntimeError("DB down")

        header = _make_sba_csv_header()
        rows = [_make_sba_csv_data_row("CORP_1")]
        csv_path = _write_sba_csv_to_tempfile(header, rows)

        try:
            with pytest.raises(RuntimeError, match="SBA ingest failed"):
                ingest_sba_csv(
                    csv_file_path=csv_path,
                    extract_date="2025-09-30",
                    source_filename="test.csv",
                )
        finally:
            os.unlink(csv_path)

    @patch("app.services.sba_ingest.upsert_sba_loans")
    def test_rejected_rows_not_persisted(self, mock_upsert: MagicMock):
        from app.services.sba_ingest import ingest_sba_csv

        mock_upsert.return_value = {"rows_written": 1}

        header = _make_sba_csv_header()
        valid_row = _make_sba_csv_data_row("VALID CORP")
        empty_name_row = _make_sba_csv_data_row("")  # will be rejected
        csv_path = _write_sba_csv_to_tempfile(header, [valid_row, empty_name_row])

        try:
            result = ingest_sba_csv(
                csv_file_path=csv_path,
                extract_date="2025-09-30",
                source_filename="test.csv",
            )
            assert result["total_rows_parsed"] == 2
            assert result["total_rows_accepted"] == 1
            assert result["total_rows_rejected"] == 1
        finally:
            os.unlink(csv_path)

    def test_wrong_column_count_raises_value_error(self):
        from app.services.sba_ingest import ingest_sba_csv

        header = ["col1", "col2", "col3"]  # Wrong count
        csv_path = _write_sba_csv_to_tempfile(header, [["a", "b", "c"]])

        try:
            with pytest.raises(ValueError, match="SBA CSV header has 3 columns"):
                ingest_sba_csv(
                    csv_file_path=csv_path,
                    extract_date="2025-09-30",
                    source_filename="bad.csv",
                )
        finally:
            os.unlink(csv_path)
