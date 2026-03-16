# app/services/sba_ingest.py — SBA 7(a) loan CSV ingest orchestrator

from __future__ import annotations

import csv
import logging
import time
from typing import Any

from app.services.sba_column_map import SBA_COLUMN_COUNT
from app.services.sba_common import (
    SbaCsvRow,
    SbaSourceContext,
    parse_sba_csv_row,
    upsert_sba_loans,
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 50_000


def ingest_sba_csv(
    *,
    csv_file_path: str,
    extract_date: str,
    source_filename: str,
    source_url: str = "",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Ingest an SBA 7(a) loan CSV file, parsing and persisting in chunks.

    Args:
        csv_file_path: Path to the CSV file on the local filesystem.
        extract_date: Date of the extract in YYYY-MM-DD format (derived from asofdate).
        source_filename: Original CSV filename.
        source_url: Download URL (optional).
        chunk_size: Number of rows per persistence chunk.

    Returns:
        Summary dict with row counts and timing.
    """
    total_start = time.monotonic()

    source_context = SbaSourceContext(
        extract_date=extract_date,
        source_filename=source_filename,
        source_url=source_url,
    )

    total_rows_parsed = 0
    total_rows_accepted = 0
    total_rows_rejected = 0
    total_rows_written = 0
    chunks_processed = 0
    chunk: list[SbaCsvRow] = []

    with open(csv_file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate header column count
        if reader.fieldnames is not None:
            header_count = len(reader.fieldnames)
            if header_count != SBA_COLUMN_COUNT:
                raise ValueError(
                    f"SBA CSV header has {header_count} columns, "
                    f"expected {SBA_COLUMN_COUNT}. "
                    f"File: {source_filename}"
                )

        for row_dict in reader:
            total_rows_parsed += 1
            row_number = total_rows_parsed

            parsed = parse_sba_csv_row(row_dict, row_number)
            if parsed is None:
                total_rows_rejected += 1
                continue

            total_rows_accepted += 1
            chunk.append(parsed)

            if len(chunk) == chunk_size:
                chunk_number = chunks_processed + 1
                try:
                    result = upsert_sba_loans(
                        source_context=source_context,
                        rows=chunk,
                    )
                    total_rows_written += result.get("rows_written", 0)
                    chunks_processed += 1
                except Exception as exc:
                    logger.error(
                        "sba_ingest_chunk_failed",
                        extra={
                            "extract_date": extract_date,
                            "source_filename": source_filename,
                            "chunk_number": chunk_number,
                            "rows_parsed_so_far": total_rows_parsed,
                            "rows_written_so_far": total_rows_written,
                            "error": str(exc),
                        },
                    )
                    raise RuntimeError(
                        f"SBA ingest failed at chunk {chunk_number} "
                        f"(~row {total_rows_parsed}) for {source_filename}: {exc}"
                    ) from exc
                chunk = []

    # Flush remaining partial chunk
    if chunk:
        chunk_number = chunks_processed + 1
        try:
            result = upsert_sba_loans(
                source_context=source_context,
                rows=chunk,
            )
            total_rows_written += result.get("rows_written", 0)
            chunks_processed += 1
        except Exception as exc:
            logger.error(
                "sba_ingest_chunk_failed",
                extra={
                    "extract_date": extract_date,
                    "source_filename": source_filename,
                    "chunk_number": chunk_number,
                    "rows_parsed_so_far": total_rows_parsed,
                    "rows_written_so_far": total_rows_written,
                    "error": str(exc),
                },
            )
            raise RuntimeError(
                f"SBA ingest failed at chunk {chunk_number} "
                f"(~row {total_rows_parsed}) for {source_filename}: {exc}"
            ) from exc

    total_ms = (time.monotonic() - total_start) * 1000

    logger.info(
        "sba_ingest_csv_summary",
        extra={
            "extract_date": extract_date,
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
