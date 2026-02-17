from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

from app.contracts.pricing_intelligence import PricingIntelligenceOutput
from app.providers import revenueinfra

_OPERATION_ID = "company.derive.pricing_intelligence"
_PROVIDER = "revenueinfra"


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _coerce_to_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return str(int(value)) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _extract_inputs(input_data: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    cumulative = input_data.get("cumulative_context")
    context = cumulative if isinstance(cumulative, dict) else input_data
    company_profile = context.get("company_profile") if isinstance(context.get("company_profile"), dict) else {}

    company_domain = (
        _as_str(context.get("company_domain"))
        or _as_str(company_profile.get("company_domain"))
    )
    pricing_page_url = _as_str(context.get("pricing_page_url"))
    company_name = (
        _as_str(context.get("company_name"))
        or _as_str(company_profile.get("company_name"))
    )
    return company_domain, pricing_page_url, company_name


def _count_resolved_fields(output_data: dict[str, Any]) -> int:
    excluded = {"fields_resolved", "source_provider"}
    return sum(
        1
        for key, value in output_data.items()
        if key not in excluded and value is not None
    )


async def execute_company_derive_pricing_intelligence(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    provider_attempts: list[dict[str, Any]] = []

    company_domain, pricing_page_url, company_name = _extract_inputs(input_data)
    if not pricing_page_url:
        return {
            "run_id": run_id,
            "operation_id": _OPERATION_ID,
            "status": "failed",
            "missing_inputs": ["pricing_page_url"],
            "provider_attempts": provider_attempts,
        }

    endpoint_calls: list[
        tuple[str, str, Callable[..., Awaitable[dict[str, Any]]]]
    ] = [
        ("free_trial", "free_trial", revenueinfra.infer_free_trial),
        ("pricing_visibility", "pricing_visibility", revenueinfra.infer_pricing_visibility),
        ("sales_motion", "sales_motion", revenueinfra.infer_sales_motion),
        ("pricing_model", "pricing_model", revenueinfra.infer_pricing_model),
        ("billing_default", "billing_default", revenueinfra.infer_billing_default),
        ("number_of_tiers", "number_of_tiers", revenueinfra.infer_number_of_tiers),
        ("add_ons_offered", "add_ons_offered", revenueinfra.infer_add_ons_offered),
        ("enterprise_tier_exists", "enterprise_tier_exists", revenueinfra.infer_enterprise_tier_exists),
        ("security_compliance_gating", "security_compliance_gating", revenueinfra.infer_security_compliance_gating),
        ("annual_commitment_required", "annual_commitment_required", revenueinfra.infer_annual_commitment_required),
        ("plan_naming_style", "plan_naming_style", revenueinfra.infer_plan_naming_style),
        ("custom_pricing_mentioned", "custom_pricing_mentioned", revenueinfra.infer_custom_pricing_mentioned),
        ("money_back_guarantee", "money_back_guarantee", revenueinfra.infer_money_back_guarantee),
        ("minimum_seats", "minimum_seats", revenueinfra.infer_minimum_seats),
    ]

    raw_results: dict[str, Any] = {}
    endpoint_statuses: dict[str, str] = {}
    endpoint_failures: dict[str, Any] = {}
    failed_count = 0

    for endpoint_name, output_field, infer_fn in endpoint_calls:
        result = await infer_fn(
            domain=company_domain or "",
            pricing_page_url=pricing_page_url,
            company_name=company_name,
        )
        attempt = result.get("attempt") if isinstance(result, dict) else {}
        status = attempt.get("status") if isinstance(attempt, dict) else "failed"
        endpoint_statuses[endpoint_name] = status
        if status == "failed":
            failed_count += 1
            endpoint_failures[endpoint_name] = attempt
        mapped = result.get("mapped") if isinstance(result, dict) else {}
        raw_results[output_field] = mapped.get(output_field) if isinstance(mapped, dict) else None

    output_payload = {
        "pricing_page_url": pricing_page_url,
        "free_trial": _coerce_to_string(raw_results.get("free_trial")),
        "pricing_visibility": _coerce_to_string(raw_results.get("pricing_visibility")),
        "sales_motion": _coerce_to_string(raw_results.get("sales_motion")),
        "pricing_model": _coerce_to_string(raw_results.get("pricing_model")),
        "billing_default": _coerce_to_string(raw_results.get("billing_default")),
        "number_of_tiers": raw_results.get("number_of_tiers"),
        "add_ons_offered": _coerce_to_string(raw_results.get("add_ons_offered")),
        "enterprise_tier_exists": _coerce_to_string(raw_results.get("enterprise_tier_exists")),
        "security_compliance_gating": _coerce_to_string(raw_results.get("security_compliance_gating")),
        "annual_commitment_required": _coerce_to_string(raw_results.get("annual_commitment_required")),
        "plan_naming_style": _coerce_to_string(raw_results.get("plan_naming_style")),
        "custom_pricing_mentioned": _coerce_to_string(raw_results.get("custom_pricing_mentioned")),
        "money_back_guarantee": _coerce_to_string(raw_results.get("money_back_guarantee")),
        "minimum_seats": _coerce_to_string(raw_results.get("minimum_seats")),
        "fields_resolved": 0,
        "source_provider": _PROVIDER,
    }
    output_payload["fields_resolved"] = _count_resolved_fields(output_payload)

    try:
        output = PricingIntelligenceOutput.model_validate(output_payload).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": _OPERATION_ID,
            "status": "failed",
            "provider_attempts": [
                {
                    "provider": _PROVIDER,
                    "action": "derive_pricing_intelligence",
                    "status": "failed",
                    "provider_status": "output_validation_failed",
                    "raw_response": {
                        "endpoint_statuses": endpoint_statuses,
                        "endpoint_failures": endpoint_failures,
                    },
                }
            ],
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    overall_status = "failed" if failed_count == len(endpoint_calls) else "found"
    provider_attempts.append(
        {
            "provider": _PROVIDER,
            "action": "derive_pricing_intelligence",
            "status": overall_status,
            "provider_status": "partial" if 0 < failed_count < len(endpoint_calls) else "ok",
            "raw_response": {
                "endpoint_statuses": endpoint_statuses,
                "endpoint_failures": endpoint_failures,
            },
        }
    )

    return {
        "run_id": run_id,
        "operation_id": _OPERATION_ID,
        "status": overall_status,
        "output": output,
        "provider_attempts": provider_attempts,
    }
