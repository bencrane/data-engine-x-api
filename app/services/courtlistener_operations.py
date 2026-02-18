from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.courtlistener import (
    BankruptcyFilingSearchOutput,
    CourtFilingSearchOutput,
    DocketDetailOutput,
)
from app.providers import courtlistener

_CHECK_COURT_FILINGS_OPERATION_ID = "company.research.check_court_filings"
_BANKRUPTCY_FILINGS_OPERATION_ID = "company.signal.bankruptcy_filings"
_GET_DOCKET_DETAIL_OPERATION_ID = "company.research.get_docket_detail"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def _as_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = [parsed for item in value if (parsed := _as_str(item))]
    return cleaned or None


def _context(input_data: dict[str, Any]) -> dict[str, Any]:
    cumulative = input_data.get("cumulative_context")
    if isinstance(cumulative, dict):
        return cumulative
    return input_data


def _step_config(input_data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(input_data.get("step_config"))
    if direct:
        return direct
    return _as_dict(context.get("step_config"))


def _extract_company_name(input_data: dict[str, Any], context: dict[str, Any]) -> str | None:
    company_profile = _as_dict(context.get("company_profile"))
    output = _as_dict(context.get("output"))
    return _as_str(
        input_data.get("company_name")
        or context.get("company_name")
        or company_profile.get("company_name")
        or output.get("company_name")
    )


def _extract_dates_and_court(
    input_data: dict[str, Any], step_config: dict[str, Any]
) -> tuple[str | None, str | None, str | None]:
    court_type = _as_str(input_data.get("court_type")) or _as_str(step_config.get("court_type"))
    date_filed_gte = _as_str(input_data.get("date_filed_gte")) or _as_str(step_config.get("date_filed_gte"))
    date_filed_lte = _as_str(input_data.get("date_filed_lte")) or _as_str(step_config.get("date_filed_lte"))
    return court_type, date_filed_gte, date_filed_lte


def _extract_courts(input_data: dict[str, Any], step_config: dict[str, Any]) -> list[str] | None:
    return _as_str_list(input_data.get("courts")) or _as_str_list(step_config.get("courts"))


def _extract_docket_id(input_data: dict[str, Any], context: dict[str, Any]) -> int | None:
    direct = _as_int(input_data.get("docket_id"))
    if direct is not None:
        return direct

    direct_context = _as_int(context.get("docket_id"))
    if direct_context is not None:
        return direct_context

    output = _as_dict(context.get("output"))
    output_docket_id = _as_int(output.get("docket_id"))
    if output_docket_id is not None:
        return output_docket_id

    candidate_collections = [
        _as_list(context.get("court_filings")),
        _as_list(context.get("bankruptcy_filings")),
        _as_list(context.get("results")),
        _as_list(output.get("court_filings")),
        _as_list(output.get("results")),
    ]
    for collection in candidate_collections:
        for item in collection:
            parsed = _as_int(_as_dict(item).get("docket_id"))
            if parsed is not None:
                return parsed
    return None


def _attempt_and_mapped(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = result.get("attempt")
    mapped = result.get("mapped")
    return (
        attempt if isinstance(attempt, dict) else {},
        mapped if isinstance(mapped, dict) else {},
    )


async def execute_company_research_check_court_filings(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)
    step_config = _step_config(input_data, context)

    company_name = _extract_company_name(input_data, context)
    if not company_name:
        return {
            "run_id": run_id,
            "operation_id": _CHECK_COURT_FILINGS_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["company_name"],
            "provider_attempts": provider_attempts,
        }

    court_type, date_filed_gte, date_filed_lte = _extract_dates_and_court(input_data, step_config)
    settings = get_settings()
    adapter_result = await courtlistener.search_court_filings(
        api_key=settings.courtlistener_api_key,
        company_name=company_name,
        court_type=court_type,
        date_filed_gte=date_filed_gte,
        date_filed_lte=date_filed_lte,
    )
    attempt, mapped = _attempt_and_mapped(adapter_result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _CHECK_COURT_FILINGS_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    try:
        output = CourtFilingSearchOutput.model_validate(
            {
                **mapped,
                "source_provider": "courtlistener",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _CHECK_COURT_FILINGS_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": _CHECK_COURT_FILINGS_OPERATION_ID,
        "status": "not_found" if status == "not_found" else "found",
        "output": {
            **output,
            "court_filings": output["results"],
            "court_filing_count": output["result_count"],
        },
        "provider_attempts": provider_attempts,
    }


async def execute_company_signal_bankruptcy_filings(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)
    step_config = _step_config(input_data, context)
    date_filed_gte = _as_str(input_data.get("date_filed_gte")) or _as_str(step_config.get("date_filed_gte"))
    date_filed_lte = _as_str(input_data.get("date_filed_lte")) or _as_str(step_config.get("date_filed_lte"))
    courts = _extract_courts(input_data, step_config)

    if not date_filed_gte:
        return {
            "run_id": run_id,
            "operation_id": _BANKRUPTCY_FILINGS_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["date_filed_gte"],
            "provider_attempts": provider_attempts,
        }

    settings = get_settings()
    adapter_result = await courtlistener.search_bankruptcy_filings(
        api_key=settings.courtlistener_api_key,
        date_filed_gte=date_filed_gte,
        date_filed_lte=date_filed_lte,
        courts=courts,
    )
    attempt, mapped = _attempt_and_mapped(adapter_result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _BANKRUPTCY_FILINGS_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    try:
        output = BankruptcyFilingSearchOutput.model_validate(
            {
                **mapped,
                "source_provider": "courtlistener",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _BANKRUPTCY_FILINGS_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    # Each result is a bankruptcy docket that can be fanned out downstream.
    return {
        "run_id": run_id,
        "operation_id": _BANKRUPTCY_FILINGS_OPERATION_ID,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }


async def execute_company_research_get_docket_detail(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []
    context = _context(input_data)
    docket_id = _extract_docket_id(input_data, context)
    if docket_id is None:
        return {
            "run_id": run_id,
            "operation_id": _GET_DOCKET_DETAIL_OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["docket_id"],
            "provider_attempts": provider_attempts,
        }

    settings = get_settings()
    adapter_result = await courtlistener.get_docket_detail(
        api_key=settings.courtlistener_api_key,
        docket_id=docket_id,
    )
    attempt, mapped = _attempt_and_mapped(adapter_result)
    provider_attempts.append(attempt)
    status = attempt.get("status")
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": _GET_DOCKET_DETAIL_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
        }

    try:
        output = DocketDetailOutput.model_validate(
            {
                **mapped,
                "source_provider": "courtlistener",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _GET_DOCKET_DETAIL_OPERATION_ID,
            "status": "failed",
            "provider_attempts": provider_attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": _GET_DOCKET_DETAIL_OPERATION_ID,
        "status": "found",
        "output": output,
        "provider_attempts": provider_attempts,
    }
