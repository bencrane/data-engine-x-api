from __future__ import annotations

import re
import uuid
from typing import Any

from app.config import get_settings
from app.contracts.sec_filings import FetchSECFilingsOutput, SECAnalysisOutput
from app.providers import revenueinfra

_FETCH_OPERATION_ID = "company.research.fetch_sec_filings"
_ANALYZE_10K_OPERATION_ID = "company.analyze.sec_10k"
_ANALYZE_10Q_OPERATION_ID = "company.analyze.sec_10q"
_ANALYZE_8K_EXECUTIVE_OPERATION_ID = "company.analyze.sec_8k_executive"
_PROVIDER = "revenueinfra"


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _context(input_data: dict[str, Any]) -> dict[str, Any]:
    cumulative = input_data.get("cumulative_context")
    if isinstance(cumulative, dict):
        return cumulative
    return input_data


def _company_domain(input_data: dict[str, Any], context: dict[str, Any]) -> str | None:
    company_profile = _as_dict(context.get("company_profile"))
    return _as_str(
        input_data.get("company_domain")
        or context.get("company_domain")
        or company_profile.get("company_domain")
    )


def _company_name(input_data: dict[str, Any], context: dict[str, Any]) -> str | None:
    company_profile = _as_dict(context.get("company_profile"))
    return _as_str(
        input_data.get("company_name")
        or context.get("company_name")
        or company_profile.get("company_name")
    )


def _get_path(source: Any, path: str) -> Any:
    current = source
    for segment in path.split("."):
        match = re.fullmatch(r"([A-Za-z0-9_]+)(?:\[(\d+)])?", segment)
        if match is None:
            return None
        key = match.group(1)
        idx_raw = match.group(2)
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if idx_raw is not None:
            if not isinstance(current, list):
                return None
            idx = int(idx_raw)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
    return current


def _attempt_dict(result: dict[str, Any]) -> dict[str, Any]:
    attempt = result.get("attempt")
    return attempt if isinstance(attempt, dict) else {}


def _mapped_dict(result: dict[str, Any]) -> dict[str, Any]:
    mapped = result.get("mapped")
    return mapped if isinstance(mapped, dict) else {}


async def execute_company_research_fetch_sec_filings(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)

    company_domain = _company_domain(input_data, context)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": _FETCH_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": provider_attempts,
        }

    settings = get_settings()
    result = await revenueinfra.fetch_sec_filings(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = _attempt_dict(result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _FETCH_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    mapped = _mapped_dict(result)
    output_payload = {
        "cik": _as_str(mapped.get("cik")),
        "ticker": _as_str(mapped.get("ticker")),
        "company_name": _as_str(mapped.get("company_name")) or _company_name(input_data, context),
        "latest_10k": mapped.get("latest_10k"),
        "latest_10q": mapped.get("latest_10q"),
        "recent_8k_executive_changes": mapped.get("recent_8k_executive_changes"),
        "recent_8k_earnings": mapped.get("recent_8k_earnings"),
        "recent_8k_material_contracts": mapped.get("recent_8k_material_contracts"),
        "source_provider": _PROVIDER,
    }

    try:
        output = FetchSECFilingsOutput.model_validate(output_payload).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _FETCH_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": _FETCH_OPERATION_ID,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }


async def execute_company_analyze_sec_10k(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)

    document_url = _as_str(
        input_data.get("document_url")
        or _get_path(context, "latest_10k.document_url")
    )
    if not document_url:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_10K_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["latest_10k.document_url"],
            "provider_attempts": provider_attempts,
        }

    domain = _company_domain(input_data, context)
    company_name = _company_name(input_data, context)
    result = await revenueinfra.analyze_10k(
        document_url=document_url,
        domain=domain,
        company_name=company_name,
    )
    attempt = _attempt_dict(result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_10K_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    mapped = _mapped_dict(result)
    output_payload = {
        "filing_type": _as_str(mapped.get("filing_type")) or "10-K",
        "document_url": _as_str(mapped.get("document_url")) or document_url,
        "domain": _as_str(mapped.get("domain")) or domain,
        "company_name": _as_str(mapped.get("company_name")) or company_name,
        "analysis": _as_str(mapped.get("analysis")),
        "source_provider": _PROVIDER,
    }
    try:
        output = SECAnalysisOutput.model_validate(output_payload).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_10K_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": _ANALYZE_10K_OPERATION_ID,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }


async def execute_company_analyze_sec_10q(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)

    document_url = _as_str(
        input_data.get("document_url")
        or _get_path(context, "latest_10q.document_url")
    )
    if not document_url:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_10Q_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["latest_10q.document_url"],
            "provider_attempts": provider_attempts,
        }

    domain = _company_domain(input_data, context)
    company_name = _company_name(input_data, context)
    result = await revenueinfra.analyze_10q(
        document_url=document_url,
        domain=domain,
        company_name=company_name,
    )
    attempt = _attempt_dict(result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_10Q_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    mapped = _mapped_dict(result)
    output_payload = {
        "filing_type": _as_str(mapped.get("filing_type")) or "10-Q",
        "document_url": _as_str(mapped.get("document_url")) or document_url,
        "domain": _as_str(mapped.get("domain")) or domain,
        "company_name": _as_str(mapped.get("company_name")) or company_name,
        "analysis": _as_str(mapped.get("analysis")),
        "source_provider": _PROVIDER,
    }
    try:
        output = SECAnalysisOutput.model_validate(output_payload).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_10Q_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": _ANALYZE_10Q_OPERATION_ID,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }


async def execute_company_analyze_sec_8k_executive(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)

    executive_filings = _as_list(_get_path(context, "recent_8k_executive_changes"))
    if not executive_filings:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_8K_EXECUTIVE_OPERATION_ID,
            "status": "not_found",
            "provider_attempts": provider_attempts,
        }

    document_url = _as_str(
        input_data.get("document_url")
        or _get_path(context, "recent_8k_executive_changes[0].document_url")
    )
    if not document_url:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_8K_EXECUTIVE_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["recent_8k_executive_changes[0].document_url"],
            "provider_attempts": provider_attempts,
        }

    domain = _company_domain(input_data, context)
    company_name = _company_name(input_data, context)
    result = await revenueinfra.analyze_8k_executive(
        document_url=document_url,
        domain=domain,
        company_name=company_name,
    )
    attempt = _attempt_dict(result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_8K_EXECUTIVE_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    mapped = _mapped_dict(result)
    output_payload = {
        "filing_type": _as_str(mapped.get("filing_type")) or "8-K-executive",
        "document_url": _as_str(mapped.get("document_url")) or document_url,
        "domain": _as_str(mapped.get("domain")) or domain,
        "company_name": _as_str(mapped.get("company_name")) or company_name,
        "analysis": _as_str(mapped.get("analysis")),
        "source_provider": _PROVIDER,
    }
    try:
        output = SECAnalysisOutput.model_validate(output_payload).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _ANALYZE_8K_EXECUTIVE_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": _ANALYZE_8K_EXECUTIVE_OPERATION_ID,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }
