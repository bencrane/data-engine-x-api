# app/services/usaspending_extract_ingest.py — USASpending.gov CSV ingest orchestrator

from __future__ import annotations

import csv
import logging
import os
import tempfile
import time
import zipfile
from typing import Any

from app.services.usaspending_column_map import (
    USASPENDING_COLUMN_COUNT,
    USASPENDING_DELTA_COLUMN_COUNT,
)
from app.services.usaspending_common import (
    UsaspendingCsvRow,
    UsaspendingSourceContext,
    parse_usaspending_csv_row,
    upsert_usaspending_contracts,
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 50_000


def ingest_usaspending_csv(
    *,
    csv_file_path: str,
    extract_date: str,
    extract_type: str,
    source_filename: str,
    is_delta: bool = False,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Ingest a single USASpending CSV file, parsing and persisting in chunks.

    Args:
        csv_file_path: Path to an extracted CSV file on the local filesystem.
        extract_date: Date of the extract in YYYY-MM-DD format.
        extract_type: FULL or DELTA.
        source_filename: Original CSV filename from the ZIP.
        is_delta: Whether this is a delta file (299 columns vs 297).
        chunk_size: Number of rows per persistence chunk.

    Returns:
        Summary dict with row counts and timing.
    """
    total_start = time.monotonic()

    source_context = UsaspendingSourceContext(
        extract_date=extract_date,
        extract_type=extract_type,
        source_filename=source_filename,
    )

    total_rows_parsed = 0
    total_rows_accepted = 0
    total_rows_rejected = 0
    total_rows_written = 0
    chunks_processed = 0
    chunk: list[UsaspendingCsvRow] = []

    expected_col_count = USASPENDING_DELTA_COLUMN_COUNT if is_delta else USASPENDING_COLUMN_COUNT

    with open(csv_file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate header column count
        if reader.fieldnames is not None:
            header_count = len(reader.fieldnames)
            if header_count != expected_col_count:
                raise ValueError(
                    f"USASpending CSV header has {header_count} columns, "
                    f"expected {expected_col_count} ({'delta' if is_delta else 'full'}). "
                    f"File: {source_filename}"
                )

        for row_dict in reader:
            total_rows_parsed += 1
            row_number = total_rows_parsed

            parsed = parse_usaspending_csv_row(row_dict, row_number, is_delta=is_delta)
            if parsed is None:
                total_rows_rejected += 1
                continue

            total_rows_accepted += 1
            chunk.append(parsed)

            if len(chunk) == chunk_size:
                chunk_number = chunks_processed + 1
                try:
                    result = upsert_usaspending_contracts(
                        source_context=source_context,
                        rows=chunk,
                        is_delta=is_delta,
                    )
                    total_rows_written += result.get("rows_written", 0)
                    chunks_processed += 1
                except Exception as exc:
                    logger.error(
                        "usaspending_ingest_chunk_failed",
                        extra={
                            "extract_date": extract_date,
                            "extract_type": extract_type,
                            "source_filename": source_filename,
                            "chunk_number": chunk_number,
                            "rows_parsed_so_far": total_rows_parsed,
                            "rows_written_so_far": total_rows_written,
                            "error": str(exc),
                        },
                    )
                    raise RuntimeError(
                        f"USASpending ingest failed at chunk {chunk_number} "
                        f"(~row {total_rows_parsed}) for {source_filename}: {exc}"
                    ) from exc
                chunk = []

    # Flush remaining partial chunk
    if chunk:
        chunk_number = chunks_processed + 1
        try:
            result = upsert_usaspending_contracts(
                source_context=source_context,
                rows=chunk,
                is_delta=is_delta,
            )
            total_rows_written += result.get("rows_written", 0)
            chunks_processed += 1
        except Exception as exc:
            logger.error(
                "usaspending_ingest_chunk_failed",
                extra={
                    "extract_date": extract_date,
                    "extract_type": extract_type,
                    "source_filename": source_filename,
                    "chunk_number": chunk_number,
                    "rows_parsed_so_far": total_rows_parsed,
                    "rows_written_so_far": total_rows_written,
                    "error": str(exc),
                },
            )
            raise RuntimeError(
                f"USASpending ingest failed at chunk {chunk_number} "
                f"(~row {total_rows_parsed}) for {source_filename}: {exc}"
            ) from exc

    total_ms = (time.monotonic() - total_start) * 1000

    logger.info(
        "usaspending_ingest_csv_summary",
        extra={
            "extract_date": extract_date,
            "extract_type": extract_type,
            "source_filename": source_filename,
            "total_rows_parsed": total_rows_parsed,
            "total_rows_accepted": total_rows_accepted,
            "total_rows_rejected": total_rows_rejected,
            "total_rows_written": total_rows_written,
            "chunks_processed": chunks_processed,
            "total_ms": round(total_ms, 1),
        },
    )

    return {
        "source_filename": source_filename,
        "total_rows_parsed": total_rows_parsed,
        "total_rows_accepted": total_rows_accepted,
        "total_rows_rejected": total_rows_rejected,
        "total_rows_written": total_rows_written,
        "chunks_processed": chunks_processed,
        "total_elapsed_ms": round(total_ms, 1),
    }


def ingest_usaspending_zip(
    *,
    zip_file_path: str,
    extract_date: str,
    extract_type: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Ingest all CSV files from a USASpending ZIP archive.

    Args:
        zip_file_path: Path to the ZIP file containing one or more CSVs.
        extract_date: Date of the extract in YYYY-MM-DD format.
        extract_type: FULL or DELTA.
        chunk_size: Number of rows per persistence chunk.

    Returns:
        Combined summary dict with per-file breakdowns.
    """
    total_start = time.monotonic()
    is_delta = extract_type.upper() == "DELTA"

    if not os.path.exists(zip_file_path):
        raise ValueError(f"ZIP file not found: {zip_file_path}")

    with zipfile.ZipFile(zip_file_path, "r") as zf:
        csv_names = sorted(n for n in zf.namelist() if n.endswith(".csv"))
        if not csv_names:
            raise ValueError(f"No CSV files found in ZIP: {zip_file_path}")

        logger.info(
            "usaspending_ingest_zip_start",
            extra={
                "zip_file_path": zip_file_path,
                "extract_date": extract_date,
                "extract_type": extract_type,
                "csv_count": len(csv_names),
                "csv_files": csv_names,
            },
        )

        file_results: list[dict[str, Any]] = []
        agg_parsed = 0
        agg_accepted = 0
        agg_rejected = 0
        agg_written = 0
        agg_chunks = 0

        for csv_name in csv_names:
            # Extract CSV to temp file
            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".csv", delete=False
            ) as tmp:
                tmp_path = tmp.name
                tmp.write(zf.read(csv_name))

            try:
                file_result = ingest_usaspending_csv(
                    csv_file_path=tmp_path,
                    extract_date=extract_date,
                    extract_type=extract_type,
                    source_filename=csv_name,
                    is_delta=is_delta,
                    chunk_size=chunk_size,
                )
                file_results.append(file_result)
                agg_parsed += file_result["total_rows_parsed"]
                agg_accepted += file_result["total_rows_accepted"]
                agg_rejected += file_result["total_rows_rejected"]
                agg_written += file_result["total_rows_written"]
                agg_chunks += file_result["chunks_processed"]
            finally:
                os.unlink(tmp_path)

    total_ms = (time.monotonic() - total_start) * 1000

    logger.info(
        "usaspending_ingest_zip_summary",
        extra={
            "zip_file_path": zip_file_path,
            "extract_date": extract_date,
            "extract_type": extract_type,
            "csv_files_processed": len(file_results),
            "total_rows_parsed": agg_parsed,
            "total_rows_written": agg_written,
            "total_ms": round(total_ms, 1),
        },
    )

    return {
        "extract_date": extract_date,
        "extract_type": extract_type,
        "zip_file_path": zip_file_path,
        "csv_files_processed": len(file_results),
        "total_rows_parsed": agg_parsed,
        "total_rows_accepted": agg_accepted,
        "total_rows_rejected": agg_rejected,
        "total_rows_written": agg_written,
        "total_chunks_processed": agg_chunks,
        "total_elapsed_ms": round(total_ms, 1),
        "file_results": file_results,
    }
