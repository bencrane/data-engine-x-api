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
    account_number = _as_int(input_data.get("account_number"), default=1, minimum=1)
    max_pages = _as_int(
        input_data.get("max_pages") or options.get("max_pages") or context.get("max_pages"),
        default=50,
        minimum=1,
    )

    if not sales_nav_url:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["sales_nav_url"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    all_results: list[dict[str, Any]] = []
    current_page = 1
    total_available: int | None = None

    while current_page <= max_pages:
        provider_result = await rapidapi_salesnav.scrape_sales_nav_url(
            api_key=settings.rapidapi_salesnav_scrape_api_key,
            sales_nav_url=sales_nav_url,
            page=current_page,
            account_number=account_number,
        )
        attempt = _as_dict(provider_result.get("attempt"))
        attempts.append(attempt)

        provider_status = attempt.get("status", "failed")
        if provider_status in {"failed", "skipped"}:
            break

        mapped = _as_dict(provider_result.get("mapped"))
        page_results = mapped.get("results")
        if not isinstance(page_results, list):
            page_results = []

        all_results.extend(page_results)

        if total_available is None:
            total_available = mapped.get("total_available")

        if len(page_results) == 0:
            break

        if isinstance(total_available, int) and len(all_results) >= total_available:
            break

        current_page += 1

    try:
        output = SalesNavSearchOutput.model_validate(
            {
                "results": all_results,
                "result_count": len(all_results),
                "total_available": total_available,
                "page": current_page,
                "pages_fetched": current_page if all_results else 0,
                "source_url": sales_nav_url,
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

    if not all_results and attempts:
        last_attempt = attempts[-1]
        last_status = last_attempt.get("status", "failed")
        if last_status in {"failed", "skipped"}:
            status = "failed"
        else:
            status = "not_found"
    else:
        status = "found" if all_results else "not_found"

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }
