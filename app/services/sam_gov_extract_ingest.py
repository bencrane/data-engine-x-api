# app/services/sam_gov_extract_ingest.py — SAM.gov extract ingest orchestrator

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.sam_gov_common import (
    SamGovExtractRow,
    SamGovSourceContext,
    parse_sam_gov_dat_line,
    upsert_sam_gov_entities,
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 50_000


def ingest_sam_gov_extract(
    *,
    extract_file_path: str,
    extract_date: str,
    extract_type: str,
    source_filename: str,
    source_download_url: str | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> dict[str, Any]:
    """Ingest a SAM.gov .dat extract file, parsing and persisting in chunks.

    Args:
        extract_file_path: Path to the unzipped .dat file on the local filesystem.
        extract_date: Date of the extract in YYYY-MM-DD format.
        extract_type: MONTHLY or DAILY.
        source_filename: Original .dat filename from the ZIP.
        source_download_url: URL the ZIP was downloaded from.
        chunk_size: Number of rows per persistence chunk.

    Returns:
        Summary dict with row counts and timing.
    """
    total_start = time.monotonic()

    source_context = SamGovSourceContext(
        extract_date=extract_date,
        extract_type=extract_type,
        source_filename=source_filename,
        source_download_url=source_download_url or "",
    )

    total_rows_parsed = 0
    total_rows_accepted = 0
    total_rows_rejected = 0
    total_rows_written = 0
    chunks_processed = 0
    bof_skipped = False
    expected_record_count: int | None = None
    chunk: list[SamGovExtractRow] = []

    with open(extract_file_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.rstrip("\n").rstrip("\r")
            if not stripped:
                continue

            # Skip BOF header line (first non-empty line starting with "BOF")
            if not bof_skipped and stripped.startswith("BOF"):
                bof_skipped = True
                # Parse expected record count from BOF (6th space-separated token, index 5)
                # BOF line format: BOF PUBLIC V2 00000000 20260301 0874709 0008190
                bof_tokens = stripped.split()
                if len(bof_tokens) >= 6:
                    try:
                        expected_record_count = int(bof_tokens[5])
                    except ValueError:
                        pass
                logger.info(
                    "sam_gov_ingest_bof_header",
                    extra={
                        "bof_line": stripped,
                        "expected_record_count": expected_record_count,
                        "source_filename": source_filename,
                    },
                )
                continue

            total_rows_parsed += 1
            row_number = total_rows_parsed

            parsed = parse_sam_gov_dat_line(stripped, row_number)
            if parsed is None:
                total_rows_rejected += 1
                continue

            total_rows_accepted += 1
            chunk.append(parsed)

            if len(chunk) == chunk_size:
                chunk_number = chunks_processed + 1
                try:
                    result = upsert_sam_gov_entities(
                        source_context=source_context,
                        rows=chunk,
                    )
                    total_rows_written += result.get("rows_written", 0)
                    chunks_processed += 1
                except Exception as exc:
                    logger.error(
                        "sam_gov_ingest_chunk_failed",
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
                        f"SAM.gov ingest failed at chunk {chunk_number} "
                        f"(~row {total_rows_parsed}) for {source_filename}: {exc}"
                    ) from exc
                chunk = []

    # Flush remaining partial chunk
    if chunk:
        chunk_number = chunks_processed + 1
        try:
            result = upsert_sam_gov_entities(
                source_context=source_context,
                rows=chunk,
            )
            total_rows_written += result.get("rows_written", 0)
            chunks_processed += 1
        except Exception as exc:
            logger.error(
                "sam_gov_ingest_chunk_failed",
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
                f"SAM.gov ingest failed at chunk {chunk_number} "
                f"(~row {total_rows_parsed}) for {source_filename}: {exc}"
            ) from exc

    total_ms = (time.monotonic() - total_start) * 1000

    logger.info(
        "sam_gov_ingest_summary",
        extra={
            "extract_date": extract_date,
            "extract_type": extract_type,
            "source_filename": source_filename,
            "total_rows_parsed": total_rows_parsed,
            "total_rows_accepted": total_rows_accepted,
            "total_rows_rejected": total_rows_rejected,
            "total_rows_written": total_rows_written,
            "chunks_processed": chunks_processed,
            "expected_record_count": expected_record_count,
            "total_ms": round(total_ms, 1),
        },
    )

    return {
        "extract_date": extract_date,
        "extract_type": extract_type,
        "source_filename": source_filename,
        "total_rows_parsed": total_rows_parsed,
        "total_rows_accepted": total_rows_accepted,
        "total_rows_rejected": total_rows_rejected,
        "total_rows_written": total_rows_written,
        "chunks_processed": chunks_processed,
        "total_elapsed_ms": round(total_ms, 1),
    }
