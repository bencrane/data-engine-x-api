from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.sales_nav import SalesNavSearchOutput
from app.providers import rapidapi_salesnav


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any, *, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed >= minimum else minimum


async def execute_person_search_sales_nav_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "person.search.sales_nav_url"
    attempts: list[dict[str, Any]] = []

    context = _as_dict(input_data.get("cumulative_context"))
    options = _as_dict(input_data.get("options"))

    sales_nav_url = _as_non_empty_str(
        input_data.get("sales_nav_url")
        or context.get("sales_nav_url")
    )
    page = _as_int(input_data.get("page") or options.get("page"), default=1, minimum=1)
    account_number = _as_int(input_data.get("account_number"), default=1, minimum=1)

    if not sales_nav_url:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["sales_nav_url"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key=settings.rapidapi_salesnav_scrape_api_key,
        sales_nav_url=sales_nav_url,
        page=page,
        account_number=account_number,
    )
    attempt = _as_dict(provider_result.get("attempt"))
    attempts.append(attempt)

    mapped = _as_dict(provider_result.get("mapped"))
    try:
        output = SalesNavSearchOutput.model_validate(
            {
                "results": mapped.get("results"),
                "result_count": mapped.get("result_count"),
                "total_available": mapped.get("total_available"),
                "page": mapped.get("page"),
                "source_url": mapped.get("source_url"),
                "source_provider": "rapidapi_salesnav",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    provider_status = attempt.get("status", "failed")
    if provider_status in {"failed", "skipped"}:
        status = "failed"
    elif provider_status == "not_found":
        status = "not_found"
    else:
        result_count = output.get("result_count")
        status = "found" if isinstance(result_count, int) and result_count > 0 else "not_found"

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }
