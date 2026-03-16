# tests/test_sam_gov_ingest.py — SAM.gov ingestion tests

from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from app.services.sam_gov_column_map import (
    SAM_GOV_COLUMN_COUNT,
    SAM_GOV_COLUMNS,
    SAM_GOV_DB_COLUMN_NAMES,
)
from app.services.sam_gov_common import (
    build_sam_gov_entity_row,
    parse_sam_gov_dat_line,
    SamGovSourceContext,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_pipe_line(fields: list[str] | None = None) -> str:
    """Build a valid 142-field pipe-delimited line with !end marker."""
    if fields is None:
        fields = [""] * SAM_GOV_COLUMN_COUNT
    fields[0] = fields[0] or "F847A1795DE4"  # UEI
    fields[5] = fields[5] or "A"             # SAM Extract Code
    fields[11] = fields[11] or "ACME CORP"   # Legal Business Name
    fields[-1] = "!end"
    return "|".join(fields)


def _make_source_context() -> SamGovSourceContext:
    return SamGovSourceContext(
        extract_date="2026-03-01",
        extract_type="MONTHLY",
        source_filename="SAM_PUBLIC_MONTHLY_20260301.dat",
        source_download_url="https://example.com/test.zip",
    )


# ── Column Map Tests ──────────────────────────────────────────────────────


class TestColumnMap:
    def test_column_count_is_142(self):
        assert SAM_GOV_COLUMN_COUNT == 142

    def test_first_column_is_unique_entity_id(self):
        assert SAM_GOV_COLUMNS[0]["v2_position"] == 1
        assert SAM_GOV_COLUMNS[0]["db_column_name"] == "unique_entity_id"

    def test_last_column_is_end_of_record(self):
        assert SAM_GOV_COLUMNS[-1]["v2_position"] == 142
        assert SAM_GOV_COLUMNS[-1]["db_column_name"] == "end_of_record_indicator"

    def test_column_6_is_sam_extract_code(self):
        col6 = SAM_GOV_COLUMNS[5]  # zero-indexed
        assert col6["v2_position"] == 6
        assert col6["db_column_name"] == "sam_extract_code"

    def test_column_12_is_legal_business_name(self):
        col12 = SAM_GOV_COLUMNS[11]  # zero-indexed
        assert col12["v2_position"] == 12
        assert col12["db_column_name"] == "legal_business_name"

    def test_all_db_column_names_are_valid_identifiers(self):
        identifier_pattern = re.compile(r"^[a-z_][a-z0-9_]*$")
        for col in SAM_GOV_COLUMNS:
            assert identifier_pattern.fullmatch(col["db_column_name"]), (
                f"Invalid identifier at V2 position {col['v2_position']}: "
                f"{col['db_column_name']!r}"
            )

    def test_no_duplicate_db_column_names(self):
        names = [col["db_column_name"] for col in SAM_GOV_COLUMNS]
        assert len(names) == len(set(names)), (
            f"Duplicate column names found: "
            f"{[n for n in names if names.count(n) > 1]}"
        )

    def test_db_column_names_list_matches_columns(self):
        assert SAM_GOV_DB_COLUMN_NAMES == [
            col["db_column_name"] for col in SAM_GOV_COLUMNS
        ]


# ── Line Parser Tests ─────────────────────────────────────────────────────


class TestLineParser:
    def test_valid_line_parses_correctly(self):
        line = _make_pipe_line()
        result = parse_sam_gov_dat_line(line, row_number=1)
        assert result is not None
        assert result["row_number"] == 1
        assert result["raw_line"] == line
        assert len(result["fields"]) == 142
        assert result["fields"][0] == "F847A1795DE4"
        assert result["fields"][-1] == "!end"

    def test_wrong_field_count_returns_none(self):
        # Only 10 fields instead of 142
        line = "|".join(["field"] * 10)
        result = parse_sam_gov_dat_line(line, row_number=1)
        assert result is None

    def test_missing_end_marker_returns_none(self):
        fields = [""] * SAM_GOV_COLUMN_COUNT
        fields[0] = "F847A1795DE4"
        fields[-1] = "WRONG"
        line = "|".join(fields)
        result = parse_sam_gov_dat_line(line, row_number=1)
        assert result is None

    def test_extra_fields_returns_none(self):
        fields = [""] * (SAM_GOV_COLUMN_COUNT + 5)
        fields[-1] = "!end"
        line = "|".join(fields)
        result = parse_sam_gov_dat_line(line, row_number=1)
        assert result is None

    def test_newline_stripped(self):
        line = _make_pipe_line() + "\n"
        result = parse_sam_gov_dat_line(line, row_number=1)
        assert result is not None
        assert "\n" not in result["raw_line"]


# ── Row Builder Tests ─────────────────────────────────────────────────────


class TestRowBuilder:
    def test_positional_fields_map_correctly(self):
        fields = [""] * SAM_GOV_COLUMN_COUNT
        fields[0] = "F847A1795DE4"
        fields[5] = "A"
        fields[11] = "ACME CORP"
        fields[32] = "541511"  # primary_naics (V2 position 33, zero-indexed 32)
        fields[-1] = "!end"
        line = "|".join(fields)

        parsed = parse_sam_gov_dat_line(line, row_number=42)
        assert parsed is not None

        row = build_sam_gov_entity_row(parsed, _make_source_context())

        assert row["unique_entity_id"] == "F847A1795DE4"
        assert row["sam_extract_code"] == "A"
        assert row["legal_business_name"] == "ACME CORP"
        assert row["primary_naics"] == "541511"
        assert row["end_of_record_indicator"] == "!end"

    def test_extract_metadata_populated(self):
        parsed = parse_sam_gov_dat_line(_make_pipe_line(), row_number=7)
        assert parsed is not None
        ctx = _make_source_context()
        row = build_sam_gov_entity_row(parsed, ctx)

        assert row["extract_date"] == "2026-03-01"
        assert row["extract_type"] == "MONTHLY"
        assert row["extract_code"] == "A"
        assert row["source_filename"] == "SAM_PUBLIC_MONTHLY_20260301.dat"
        assert row["source_provider"] == "sam_gov"
        assert row["row_position"] == 7

    def test_extract_code_from_correct_position(self):
        fields = [""] * SAM_GOV_COLUMN_COUNT
        fields[0] = "TEST12345678"
        fields[5] = "3"  # Updated Active
        fields[-1] = "!end"
        line = "|".join(fields)

        parsed = parse_sam_gov_dat_line(line, row_number=1)
        assert parsed is not None
        row = build_sam_gov_entity_row(parsed, _make_source_context())
        assert row["extract_code"] == "3"

    def test_empty_fields_become_none(self):
        fields = [""] * SAM_GOV_COLUMN_COUNT
        fields[0] = "F847A1795DE4"
        fields[-1] = "!end"
        line = "|".join(fields)

        parsed = parse_sam_gov_dat_line(line, row_number=1)
        assert parsed is not None
        row = build_sam_gov_entity_row(parsed, _make_source_context())

        # col_002_deprecated should be None (empty string)
        assert row["col_002_deprecated"] is None

    def test_whitespace_only_fields_become_none(self):
        fields = [""] * SAM_GOV_COLUMN_COUNT
        fields[0] = "F847A1795DE4"
        fields[11] = "   "  # whitespace-only legal business name
        fields[-1] = "!end"
        line = "|".join(fields)

        parsed = parse_sam_gov_dat_line(line, row_number=1)
        assert parsed is not None
        row = build_sam_gov_entity_row(parsed, _make_source_context())
        assert row["legal_business_name"] is None

    def test_raw_source_row_preserved(self):
        line = _make_pipe_line()
        parsed = parse_sam_gov_dat_line(line, row_number=1)
        assert parsed is not None
        row = build_sam_gov_entity_row(parsed, _make_source_context())
        assert row["raw_source_row"] == line


# ── Ingest Service Tests ──────────────────────────────────────────────────


class TestIngestService:
    def test_chunking_correct_number_of_chunks(self, tmp_path):
        """Feed 150K rows with chunk_size=50K, verify 3 chunks."""
        dat_file = tmp_path / "test.dat"
        line = _make_pipe_line()

        # Write 150K lines
        row_count = 150_000
        with open(dat_file, "w") as f:
            for _ in range(row_count):
                f.write(line + "\n")

        chunk_calls = []

        def mock_upsert(*, source_context, rows):
            chunk_calls.append(len(rows))
            return {"rows_written": len(rows)}

        with patch(
            "app.services.sam_gov_extract_ingest.upsert_sam_gov_entities",
            side_effect=mock_upsert,
        ):
            from app.services.sam_gov_extract_ingest import ingest_sam_gov_extract

            result = ingest_sam_gov_extract(
                extract_file_path=str(dat_file),
                extract_date="2026-03-01",
                extract_type="MONTHLY",
                source_filename="test.dat",
                chunk_size=50_000,
            )

        assert len(chunk_calls) == 3
        assert all(c == 50_000 for c in chunk_calls)
        assert result["total_rows_parsed"] == row_count
        assert result["total_rows_accepted"] == row_count
        assert result["total_rows_rejected"] == 0
        assert result["total_rows_written"] == row_count
        assert result["chunks_processed"] == 3

    def test_error_propagation_not_swallowed(self, tmp_path):
        """If a chunk fails, the error is re-raised (not swallowed)."""
        dat_file = tmp_path / "test.dat"
        line = _make_pipe_line()

        with open(dat_file, "w") as f:
            for _ in range(100):
                f.write(line + "\n")

        def mock_upsert_fail(*, source_context, rows):
            raise RuntimeError("DB connection failed")

        with patch(
            "app.services.sam_gov_extract_ingest.upsert_sam_gov_entities",
            side_effect=mock_upsert_fail,
        ):
            from app.services.sam_gov_extract_ingest import ingest_sam_gov_extract

            with pytest.raises(RuntimeError, match="SAM.gov ingest failed"):
                ingest_sam_gov_extract(
                    extract_file_path=str(dat_file),
                    extract_date="2026-03-01",
                    extract_type="MONTHLY",
                    source_filename="test.dat",
                    chunk_size=50,
                )

    def test_rejected_rows_counted(self, tmp_path):
        """Bad lines are counted as rejected, not silently dropped."""
        dat_file = tmp_path / "test.dat"
        good_line = _make_pipe_line()
        bad_line = "only|five|fields|here|bad"

        with open(dat_file, "w") as f:
            f.write(good_line + "\n")
            f.write(bad_line + "\n")
            f.write(good_line + "\n")

        def mock_upsert(*, source_context, rows):
            return {"rows_written": len(rows)}

        with patch(
            "app.services.sam_gov_extract_ingest.upsert_sam_gov_entities",
            side_effect=mock_upsert,
        ):
            from app.services.sam_gov_extract_ingest import ingest_sam_gov_extract

            result = ingest_sam_gov_extract(
                extract_file_path=str(dat_file),
                extract_date="2026-03-01",
                extract_type="MONTHLY",
                source_filename="test.dat",
            )

        assert result["total_rows_parsed"] == 3
        assert result["total_rows_accepted"] == 2
        assert result["total_rows_rejected"] == 1
        assert result["total_rows_written"] == 2

    def test_correctly_shaped_rows_passed_to_upsert(self, tmp_path):
        """Verify upsert receives correctly shaped rows."""
        dat_file = tmp_path / "test.dat"
        line = _make_pipe_line()

        with open(dat_file, "w") as f:
            f.write(line + "\n")

        captured_rows = []

        def mock_upsert(*, source_context, rows):
            captured_rows.extend(rows)
            return {"rows_written": len(rows)}

        with patch(
            "app.services.sam_gov_extract_ingest.upsert_sam_gov_entities",
            side_effect=mock_upsert,
        ):
            from app.services.sam_gov_extract_ingest import ingest_sam_gov_extract

            ingest_sam_gov_extract(
                extract_file_path=str(dat_file),
                extract_date="2026-03-01",
                extract_type="MONTHLY",
                source_filename="test.dat",
            )

        assert len(captured_rows) == 1
        row = captured_rows[0]
        assert row["row_number"] == 1
        assert len(row["fields"]) == 142
        assert row["fields"][0] == "F847A1795DE4"

    def test_bof_line_skipped(self, tmp_path):
        """BOF header line is skipped and not parsed as a data row."""
        dat_file = tmp_path / "test.dat"
        bof_line = "BOF PUBLIC V2 00000000 20260301 0000002 0000001"
        good_line = _make_pipe_line()

        with open(dat_file, "w") as f:
            f.write(bof_line + "\n")
            f.write(good_line + "\n")
            f.write(good_line + "\n")

        captured_rows = []

        def mock_upsert(*, source_context, rows):
            captured_rows.extend(rows)
            return {"rows_written": len(rows)}

        with patch(
            "app.services.sam_gov_extract_ingest.upsert_sam_gov_entities",
            side_effect=mock_upsert,
        ):
            from app.services.sam_gov_extract_ingest import ingest_sam_gov_extract

            result = ingest_sam_gov_extract(
                extract_file_path=str(dat_file),
                extract_date="2026-03-01",
                extract_type="MONTHLY",
                source_filename="test.dat",
            )

        # BOF line should not be counted in parsed rows
        assert result["total_rows_parsed"] == 2
        assert result["total_rows_accepted"] == 2
        assert result["total_rows_rejected"] == 0
        assert result["total_rows_written"] == 2
        assert len(captured_rows) == 2
