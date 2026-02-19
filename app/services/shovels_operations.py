from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.shovels import (
    ShovelsAddressSearchOutput,
    ShovelsContractorOutput,
    ShovelsContractorSearchOutput,
    ShovelsEmployeesOutput,
    ShovelsGeoDetailOutput,
    ShovelsGeoSearchOutput,
    ShovelsMetricsCurrentOutput,
    ShovelsMetricsMonthlyOutput,
    ShovelsPermitSearchOutput,
    ShovelsResidentsOutput,
)
from app.providers import shovels


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any, *, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _cumulative_context(input_data: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(input_data.get("cumulative_context"))


def _extract_step_config(input_data: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(input_data.get("step_config"))
    if direct:
        return direct
    return _as_dict(_cumulative_context(input_data).get("step_config"))


def _first_context_value(input_data: dict[str, Any], key: str) -> Any:
    context = _cumulative_context(input_data)
    output = _as_dict(context.get("output"))
    company_profile = _as_dict(context.get("company_profile"))
    person_profile = _as_dict(context.get("person_profile"))
    first_context_result = _as_dict(_as_list(context.get("results"))[0]) if _as_list(context.get("results")) else {}
    first_output_result = _as_dict(_as_list(output.get("results"))[0]) if _as_list(output.get("results")) else {}

    if input_data.get(key) is not None:
        return input_data.get(key)
    for candidate in (
        context.get(key),
        output.get(key),
        company_profile.get(key),
        person_profile.get(key),
        first_context_result.get(key),
        first_output_result.get(key),
    ):
        if candidate is not None:
            return candidate
    return None


def _shovels_status_from_attempt(attempt_status: str | None, has_results: bool) -> str:
    if attempt_status == "failed":
        return "failed"
    if attempt_status == "skipped":
        return "failed"
    if attempt_status == "not_found":
        return "not_found"
    if attempt_status == "found":
        return "found" if has_results else "not_found"
    return "found" if has_results else "not_found"


def _permit_search_filters(input_data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    step_config = _extract_step_config(input_data)
    filters: dict[str, Any] = {}
    for key in (
        "permit_from",
        "permit_to",
        "geo_id",
        "permit_tags",
        "property_type",
        "permit_min_job_value",
        "contractor_classification_derived",
        "size",
        "permit_has_contractor",
        "permit_q",
        "permit_status",
        "cursor",
    ):
        value = step_config.get(key)
        if value is not None:
            filters[key] = value

    missing_inputs: list[str] = []
    for key in ("permit_from", "permit_to", "geo_id"):
        if not _as_str(filters.get(key)):
            missing_inputs.append(key)
    return filters, missing_inputs


def _contractor_search_filters(input_data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    step_config = _extract_step_config(input_data)
    filters: dict[str, Any] = {}
    for key in (
        "permit_from",
        "permit_to",
        "geo_id",
        "permit_tags",
        "contractor_classification_derived",
        "contractor_name",
        "contractor_website",
        "contractor_min_total_job_value",
        "size",
        "cursor",
    ):
        value = step_config.get(key)
        if value is not None:
            filters[key] = value

    missing_inputs: list[str] = []
    for key in ("permit_from", "permit_to", "geo_id"):
        if not _as_str(filters.get(key)):
            missing_inputs.append(key)
    return filters, missing_inputs


def _market_geo_search_filters(
    input_data: dict[str, Any],
    *,
    text_key: str,
) -> tuple[dict[str, Any], list[str]]:
    step_config = _extract_step_config(input_data)
    filters: dict[str, Any] = {"state": step_config.get("state")}
    if step_config.get(text_key) is not None:
        filters[text_key] = step_config.get(text_key)
    if step_config.get("size") is not None:
        filters["size"] = step_config.get("size")

    missing_inputs: list[str] = []
    if not _as_str(filters.get("state")):
        missing_inputs.append("state")
    return filters, missing_inputs


def _address_search_filters(input_data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    step_config = _extract_step_config(input_data)
    filters: dict[str, Any] = {}
    for key in (
        "q",
        "street_no",
        "street",
        "city",
        "county",
        "state",
        "zip_code",
        "zip_code_ext",
        "jurisdiction",
        "property_type",
        "cursor",
        "size",
    ):
        if step_config.get(key) is not None:
            filters[key] = step_config.get(key)
    missing_inputs: list[str] = []
    if not _as_str(filters.get("q")):
        missing_inputs.append("q")
    return filters, missing_inputs


def _normalize_geo_type(value: Any) -> str | None:
    normalized = _as_str(value)
    if not normalized:
        return None
    lowered = normalized.lower()
    return lowered if lowered in {"city", "county", "jurisdiction", "address"} else None


async def execute_permit_search(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "permit.search"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _permit_search_filters(input_data)
    if missing_inputs:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": missing_inputs,
            "provider_attempts": attempts,
        }

    provider_result = await shovels.search_permits(
        api_key=get_settings().shovels_api_key,
        filters=filters,
    )
    attempts.append(provider_result["attempt"])

    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsPermitSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "next_cursor": mapped.get("next_cursor"),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)),
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_contractor_enrich(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "contractor.enrich"
    attempts: list[dict[str, Any]] = []

    contractor_id = _as_str(_first_context_value(input_data, "contractor_id"))
    if not contractor_id:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["contractor_id"],
            "provider_attempts": attempts,
        }

    provider_result = await shovels.get_contractor(
        api_key=get_settings().shovels_api_key,
        contractor_id=contractor_id,
    )
    attempts.append(provider_result["attempt"])

    mapped = provider_result.get("mapped")
    if not isinstance(mapped, dict):
        mapped = {}

    try:
        output = ShovelsContractorOutput.model_validate(
            {
                **mapped,
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    has_results = bool(output.get("id") or output.get("name") or output.get("business_name"))
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), has_results),
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_contractor_search(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "contractor.search"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _contractor_search_filters(input_data)
    if missing_inputs:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": missing_inputs,
            "provider_attempts": attempts,
        }

    provider_result = await shovels.search_contractors(
        api_key=get_settings().shovels_api_key,
        filters=filters,
    )
    attempts.append(provider_result["attempt"])

    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsContractorSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "next_cursor": mapped.get("next_cursor"),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)),
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_contractor_employees(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "contractor.search.employees"
    attempts: list[dict[str, Any]] = []

    contractor_id = _as_str(_first_context_value(input_data, "contractor_id"))
    if not contractor_id:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["contractor_id"],
            "provider_attempts": attempts,
        }

    step_config = _extract_step_config(input_data)
    size = _as_int(step_config.get("size"), default=50, minimum=1, maximum=100)
    cursor = _as_str(step_config.get("cursor"))

    provider_result = await shovels.get_contractor_employees(
        api_key=get_settings().shovels_api_key,
        contractor_id=contractor_id,
        size=size,
        cursor=cursor,
    )
    attempts.append(provider_result["attempt"])

    mapped = _as_dict(provider_result.get("mapped"))
    employees = _as_list(mapped.get("employees"))

    try:
        output = ShovelsEmployeesOutput.model_validate(
            {
                "employees": employees,
                "employee_count": len(employees),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(employees)),
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_address_residents(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "address.search.residents"
    attempts: list[dict[str, Any]] = []

    geo_id = _as_str(_first_context_value(input_data, "geo_id"))
    if not geo_id:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["geo_id"],
            "provider_attempts": attempts,
        }

    step_config = _extract_step_config(input_data)
    size = _as_int(step_config.get("size"), default=50, minimum=1, maximum=100)
    cursor = _as_str(step_config.get("cursor"))

    provider_result = await shovels.get_address_residents(
        api_key=get_settings().shovels_api_key,
        geo_id=geo_id,
        size=size,
        cursor=cursor,
    )
    attempts.append(provider_result["attempt"])

    mapped = _as_dict(provider_result.get("mapped"))
    residents = _as_list(mapped.get("residents"))

    try:
        output = ShovelsResidentsOutput.model_validate(
            {
                "residents": residents,
                "resident_count": len(residents),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(residents)),
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_market_search_cities(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.search.cities"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _market_geo_search_filters(input_data, text_key="name_contains")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    provider_result = await shovels.search_cities(
        api_key=get_settings().shovels_api_key,
        state=_as_str(filters.get("state")),
        name_contains=_as_str(filters.get("name_contains")),
        size=_as_int(filters.get("size"), default=50, minimum=1, maximum=100),
    )
    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsGeoSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)), "output": output, "provider_attempts": attempts}


async def execute_market_search_counties(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.search.counties"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _market_geo_search_filters(input_data, text_key="name_contains")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    provider_result = await shovels.search_counties(
        api_key=get_settings().shovels_api_key,
        state=_as_str(filters.get("state")),
        name_contains=_as_str(filters.get("name_contains")),
        size=_as_int(filters.get("size"), default=50, minimum=1, maximum=100),
    )
    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsGeoSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)), "output": output, "provider_attempts": attempts}


async def execute_market_search_zipcodes(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.search.zipcodes"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _market_geo_search_filters(input_data, text_key="zipcode_contains")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    provider_result = await shovels.search_zipcodes(
        api_key=get_settings().shovels_api_key,
        state=_as_str(filters.get("state")),
        zipcode_contains=_as_str(filters.get("zipcode_contains")),
        size=_as_int(filters.get("size"), default=50, minimum=1, maximum=100),
    )
    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsGeoSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)), "output": output, "provider_attempts": attempts}


async def execute_market_search_jurisdictions(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.search.jurisdictions"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _market_geo_search_filters(input_data, text_key="name_contains")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    provider_result = await shovels.search_jurisdictions(
        api_key=get_settings().shovels_api_key,
        state=_as_str(filters.get("state")),
        name_contains=_as_str(filters.get("name_contains")),
        size=_as_int(filters.get("size"), default=50, minimum=1, maximum=100),
    )
    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsGeoSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)), "output": output, "provider_attempts": attempts}


async def execute_market_metrics_monthly(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.enrich.metrics_monthly"
    attempts: list[dict[str, Any]] = []

    step_config = _extract_step_config(input_data)
    geo_id = _as_str(_first_context_value(input_data, "geo_id"))
    geo_type = _normalize_geo_type(step_config.get("geo_type"))
    metric = _as_str(step_config.get("metric"))
    start_date = _as_str(step_config.get("start_date"))
    end_date = _as_str(step_config.get("end_date"))

    missing_inputs: list[str] = []
    if not geo_id:
        missing_inputs.append("geo_id")
    if not geo_type:
        missing_inputs.append("geo_type")
    if not start_date:
        missing_inputs.append("start_date")
    if not end_date:
        missing_inputs.append("end_date")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    if geo_type == "city":
        provider_result = await shovels.get_city_metrics_monthly(api_key=get_settings().shovels_api_key, geo_id=geo_id, metric=metric, start_date=start_date, end_date=end_date)
    elif geo_type == "county":
        provider_result = await shovels.get_county_metrics_monthly(api_key=get_settings().shovels_api_key, geo_id=geo_id, metric=metric, start_date=start_date, end_date=end_date)
    elif geo_type == "jurisdiction":
        provider_result = await shovels.get_jurisdiction_metrics_monthly(api_key=get_settings().shovels_api_key, geo_id=geo_id, metric=metric, start_date=start_date, end_date=end_date)
    else:
        provider_result = await shovels.get_address_metrics_monthly(api_key=get_settings().shovels_api_key, geo_id=geo_id, metric=metric, start_date=start_date, end_date=end_date)

    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    data_points = _as_list(mapped.get("data_points"))

    try:
        output = ShovelsMetricsMonthlyOutput.model_validate(
            {
                "geo_id": _as_str(mapped.get("geo_id")) or geo_id,
                "metric": _as_str(mapped.get("metric")) or metric,
                "data_points": data_points,
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(data_points)), "output": output, "provider_attempts": attempts}


async def execute_market_metrics_current(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.enrich.metrics_current"
    attempts: list[dict[str, Any]] = []

    step_config = _extract_step_config(input_data)
    geo_id = _as_str(_first_context_value(input_data, "geo_id"))
    geo_type = _normalize_geo_type(step_config.get("geo_type"))

    missing_inputs: list[str] = []
    if not geo_id:
        missing_inputs.append("geo_id")
    if not geo_type:
        missing_inputs.append("geo_type")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    if geo_type == "city":
        provider_result = await shovels.get_city_metrics_current(api_key=get_settings().shovels_api_key, geo_id=geo_id)
    elif geo_type == "county":
        provider_result = await shovels.get_county_metrics_current(api_key=get_settings().shovels_api_key, geo_id=geo_id)
    elif geo_type == "jurisdiction":
        provider_result = await shovels.get_jurisdiction_metrics_current(api_key=get_settings().shovels_api_key, geo_id=geo_id)
    else:
        provider_result = await shovels.get_address_metrics_current(api_key=get_settings().shovels_api_key, geo_id=geo_id)

    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    metrics = _as_dict(mapped.get("metrics"))

    try:
        output = ShovelsMetricsCurrentOutput.model_validate(
            {
                "geo_id": _as_str(mapped.get("geo_id")) or geo_id,
                "metrics": metrics,
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(metrics)), "output": output, "provider_attempts": attempts}


async def execute_market_geo_detail(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "market.enrich.geo_detail"
    attempts: list[dict[str, Any]] = []

    step_config = _extract_step_config(input_data)
    geo_id = _as_str(_first_context_value(input_data, "geo_id"))
    geo_type = _normalize_geo_type(step_config.get("geo_type"))

    missing_inputs: list[str] = []
    if not geo_id:
        missing_inputs.append("geo_id")
    if not geo_type:
        missing_inputs.append("geo_type")
    if geo_type == "address":
        missing_inputs.append("geo_type_supported_values_city_county_jurisdiction")
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    if geo_type == "city":
        provider_result = await shovels.get_city_details(api_key=get_settings().shovels_api_key, geo_id=geo_id)
    elif geo_type == "county":
        provider_result = await shovels.get_county_details(api_key=get_settings().shovels_api_key, geo_id=geo_id)
    else:
        provider_result = await shovels.get_jurisdiction_details(api_key=get_settings().shovels_api_key, geo_id=geo_id)

    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    details = _as_dict(mapped.get("details"))

    try:
        output = ShovelsGeoDetailOutput.model_validate(
            {
                "geo_id": _as_str(mapped.get("geo_id")) or geo_id,
                "name": _as_str(mapped.get("name")),
                "state": _as_str(mapped.get("state")),
                "details": details,
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    has_results = bool(output.get("geo_id") and output.get("details"))
    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), has_results), "output": output, "provider_attempts": attempts}


async def execute_address_search(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "address.search"
    attempts: list[dict[str, Any]] = []

    filters, missing_inputs = _address_search_filters(input_data)
    if missing_inputs:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": missing_inputs, "provider_attempts": attempts}

    provider_result = await shovels.search_addresses(
        api_key=get_settings().shovels_api_key,
        filters=filters,
    )
    attempts.append(provider_result["attempt"])
    mapped = _as_dict(provider_result.get("mapped"))
    results = _as_list(mapped.get("results"))

    try:
        output = ShovelsAddressSearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "source_provider": "shovels",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "provider_attempts": attempts, "error": {"code": "output_validation_failed", "message": str(exc)}}

    return {"run_id": run_id, "operation_id": operation_id, "status": _shovels_status_from_attempt(provider_result["attempt"].get("status"), bool(results)), "output": output, "provider_attempts": attempts}
