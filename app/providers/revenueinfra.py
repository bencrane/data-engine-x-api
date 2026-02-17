from __future__ import annotations

from typing import Any, Callable

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://api.revenueinfra.com"
_TIMEOUT_SECONDS = 30.0
_PROVIDER = "revenueinfra"


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _extract_value(body: dict[str, Any], field_name: str) -> Any:
    direct = body.get(field_name)
    if direct is not None:
        return direct
    nested = body.get("data")
    if isinstance(nested, dict):
        return nested.get(field_name)
    return None


def _to_int(value: Any) -> int | None:
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
        if cleaned.endswith("+"):
            return None
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def _normalize_int_or_str(value: Any) -> int | str | None:
    as_int = _to_int(value)
    if as_int is not None:
        return as_int
    return _as_str(value)


def _normalize_yes_no(value: Any) -> bool | str | None:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if not cleaned:
        return None
    if cleaned == "yes":
        return True
    if cleaned == "no":
        return False
    return cleaned


async def _infer(
    *,
    endpoint_name: str,
    output_field: str,
    domain: str,
    pricing_page_url: str,
    company_name: str | None,
    normalize: Callable[[Any], Any] | None = None,
    endpoint_aliases: list[str] | None = None,
) -> ProviderAdapterResult:
    normalized_domain = _as_str(domain)
    normalized_pricing_page_url = _as_str(pricing_page_url)
    normalized_company_name = _as_str(company_name)

    if not normalized_domain or not normalized_pricing_page_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": f"infer_{endpoint_name.replace('-', '_')}",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {output_field: None},
        }

    payload: dict[str, Any] = {
        "domain": normalized_domain,
        "pricing_page_url": normalized_pricing_page_url,
    }
    if normalized_company_name:
        payload["company_name"] = normalized_company_name

    start_ms = now_ms()
    candidate_endpoints = [endpoint_name, *(endpoint_aliases or [])]

    body: dict[str, Any] = {}
    response: httpx.Response | None = None
    tried_endpoints: list[str] = []

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            for candidate in candidate_endpoints:
                url = f"{_BASE_URL}/run/companies/gemini/{candidate}/infer"
                tried_endpoints.append(candidate)
                response = await client.post(url, json=payload)
                body = parse_json_or_raw(response.text, response.json)
                if response.status_code != 404 or candidate == candidate_endpoints[-1]:
                    break
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": f"infer_{endpoint_name.replace('-', '_')}",
                "status": "failed",
                "error": "timeout",
                "duration_ms": now_ms() - start_ms,
            },
            "mapped": {output_field: None},
        }
    except httpx.HTTPError as exc:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": f"infer_{endpoint_name.replace('-', '_')}",
                "status": "failed",
                "error": f"http_error:{exc.__class__.__name__}",
                "duration_ms": now_ms() - start_ms,
            },
            "mapped": {output_field: None},
        }

    duration_ms = now_ms() - start_ms
    if response is None:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": f"infer_{endpoint_name.replace('-', '_')}",
                "status": "failed",
                "error": "no_response",
                "duration_ms": duration_ms,
                "raw_response": {"tried_endpoints": tried_endpoints},
            },
            "mapped": {output_field: None},
        }

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": f"infer_{endpoint_name.replace('-', '_')}",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": {"tried_endpoints": tried_endpoints, "body": body},
            },
            "mapped": {output_field: None},
        }

    value = _extract_value(body, output_field)
    if normalize is not None:
        value = normalize(value)

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": f"infer_{endpoint_name.replace('-', '_')}",
            "status": "found" if value is not None else "not_found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": {"tried_endpoints": tried_endpoints, "body": body},
        },
        "mapped": {output_field: value},
    }


async def infer_free_trial(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="free-trial",
        output_field="free_trial",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_yes_no,
    )


async def infer_pricing_visibility(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="pricing-visibility",
        output_field="pricing_visibility",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=lambda value: _as_str(value.lower()) if isinstance(value, str) else None,
    )


async def infer_sales_motion(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="sales-motion",
        output_field="sales_motion",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=lambda value: _as_str(value.lower()) if isinstance(value, str) else None,
    )


async def infer_pricing_model(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="pricing-model",
        output_field="pricing_model",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=lambda value: _as_str(value.lower()) if isinstance(value, str) else None,
    )


async def infer_billing_default(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="billing-default",
        output_field="billing_default",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=lambda value: _as_str(value.lower()) if isinstance(value, str) else None,
    )


async def infer_number_of_tiers(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="number-of-tiers",
        output_field="number_of_tiers",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_int_or_str,
    )


async def infer_add_ons_offered(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="add-ons-offered",
        output_field="add_ons_offered",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_yes_no,
    )


async def infer_enterprise_tier_exists(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="enterprise-tier-exists",
        output_field="enterprise_tier_exists",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_yes_no,
    )


async def infer_security_compliance_gating(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="security-compliance-gating",
        output_field="security_compliance_gating",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=lambda value: _as_str(value.lower()) if isinstance(value, str) else None,
        endpoint_aliases=["security-gating"],
    )


async def infer_annual_commitment_required(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="annual-commitment-required",
        output_field="annual_commitment_required",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_yes_no,
        endpoint_aliases=["annual-commitment"],
    )


async def infer_plan_naming_style(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="plan-naming-style",
        output_field="plan_naming_style",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=lambda value: _as_str(value.lower()) if isinstance(value, str) else None,
    )


async def infer_custom_pricing_mentioned(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="custom-pricing-mentioned",
        output_field="custom_pricing_mentioned",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_yes_no,
    )


async def infer_money_back_guarantee(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="money-back-guarantee",
        output_field="money_back_guarantee",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_yes_no,
    )


async def infer_minimum_seats(
    *,
    domain: str,
    pricing_page_url: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    return await _infer(
        endpoint_name="minimum-seats",
        output_field="minimum_seats",
        domain=domain,
        pricing_page_url=pricing_page_url,
        company_name=company_name,
        normalize=_normalize_int_or_str,
    )
