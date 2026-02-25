from __future__ import annotations

import uuid
from typing import Any

from app.contracts.icp_extraction import ExtractIcpTitlesOutput
from app.providers.modal_extract_icp import extract_icp_titles
from app.services.icp_job_titles import (
    query_icp_job_titles,
    update_icp_extracted_titles,
    upsert_icp_title_details_batch,
)

_OPERATION_ID = "company.derive.extract_icp_titles"


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_company_domain(value: Any) -> str | None:
    normalized = _as_non_empty_str(value)
    return normalized.lower() if isinstance(normalized, str) else None


def _context(input_data: dict[str, Any]) -> dict[str, Any]:
    cumulative_context = input_data.get("cumulative_context")
    if isinstance(cumulative_context, dict):
        return cumulative_context
    return {}


def _extract_parallel_raw_output(input_data: dict[str, Any]) -> dict[str, Any] | str | None:
    context = _context(input_data)
    parallel_raw_response = (
        context.get("parallel_raw_response")
        if isinstance(context.get("parallel_raw_response"), dict)
        else {}
    )
    parallel_output = (
        parallel_raw_response.get("output")
        if isinstance(parallel_raw_response.get("output"), dict)
        else {}
    )
    return (
        input_data.get("raw_parallel_output")
        or parallel_output.get("content")
        or context.get("raw_parallel_output")
    )


def _extract_company_domain(input_data: dict[str, Any]) -> str | None:
    context = _context(input_data)
    return _normalize_company_domain(
        input_data.get("company_domain")
        or context.get("company_domain")
    )


def _extract_raw_parallel_icp_id(input_data: dict[str, Any]) -> str | None:
    context = _context(input_data)
    return _as_non_empty_str(
        input_data.get("raw_parallel_icp_id")
        or context.get("raw_parallel_icp_id")
        or context.get("icp_job_titles_id")
    )


def _extract_org_id(input_data: dict[str, Any]) -> str | None:
    context = _context(input_data)
    return _as_non_empty_str(input_data.get("org_id") or context.get("org_id"))


async def execute_company_derive_extract_icp_titles(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []

    company_domain = _extract_company_domain(input_data)
    raw_parallel_output = _extract_parallel_raw_output(input_data)
    raw_parallel_icp_id = _extract_raw_parallel_icp_id(input_data)
    org_id = _extract_org_id(input_data)

    if company_domain and org_id and (not raw_parallel_output or not raw_parallel_icp_id):
        existing_rows = query_icp_job_titles(
            org_id=org_id,
            company_domain=company_domain,
            limit=1,
            offset=0,
        )
        if existing_rows:
            existing_row = existing_rows[0]
            if not raw_parallel_output:
                raw_parallel_output = existing_row.get("raw_parallel_output")
            if not raw_parallel_icp_id:
                raw_parallel_icp_id = _as_non_empty_str(existing_row.get("id"))

    missing_inputs: list[str] = []
    if not company_domain:
        missing_inputs.append("company_domain")
    if not raw_parallel_output:
        missing_inputs.append("raw_parallel_output")
    if not org_id:
        missing_inputs.append("org_id")
    if missing_inputs:
        return {
            "run_id": run_id,
            "operation_id": _OPERATION_ID,
            "status": "failed",
            "missing_inputs": missing_inputs,
            "provider_attempts": provider_attempts,
        }

    result = await extract_icp_titles(
        company_domain=company_domain,
        raw_parallel_output=raw_parallel_output,
        raw_parallel_icp_id=raw_parallel_icp_id,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    provider_attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    normalized_mapped = mapped if isinstance(mapped, dict) else {}
    normalized_titles = normalized_mapped.get("titles")
    if not isinstance(normalized_titles, list):
        normalized_titles = []

    try:
        output = ExtractIcpTitlesOutput.model_validate(
            {
                "company_domain": normalized_mapped.get("company_domain") or company_domain,
                "company_name": normalized_mapped.get("company_name"),
                "titles": normalized_titles,
                "title_count": normalized_mapped.get("title_count"),
                "usage": normalized_mapped.get("usage"),
                "source_provider": "modal_anthropic",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    titles = output.get("titles") if isinstance(output.get("titles"), list) else []
    updated_icp_row = update_icp_extracted_titles(
        org_id=org_id,
        company_domain=company_domain,
        extracted_titles=titles,
    )
    source_icp_job_titles_id = (
        _as_non_empty_str(updated_icp_row.get("id")) if isinstance(updated_icp_row, dict) else None
    ) or raw_parallel_icp_id
    upsert_icp_title_details_batch(
        org_id=org_id,
        company_domain=company_domain,
        company_name=_as_non_empty_str(output.get("company_name")),
        titles=titles,
        source_icp_job_titles_id=source_icp_job_titles_id,
    )

    return {
        "run_id": run_id,
        "operation_id": _OPERATION_ID,
        "status": "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }
