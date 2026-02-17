from __future__ import annotations

import pytest

from app.services import pricing_intelligence_operations


def _mock_infer(
    *,
    field_name: str,
    status: str,
    value=None,
):
    async def _stub(*, domain: str, pricing_page_url: str, company_name: str | None):
        _ = (domain, pricing_page_url, company_name)
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": f"infer_{field_name}",
                "status": status,
                "raw_response": {"mocked": True},
            },
            "mapped": {field_name: value},
        }

    return _stub


def _mock_all_endpoints(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status_by_field: dict[str, str] | None = None,
    value_by_field: dict[str, object] | None = None,
) -> None:
    status_by_field = status_by_field or {}
    value_by_field = value_by_field or {}
    field_to_func = {
        "free_trial": "infer_free_trial",
        "pricing_visibility": "infer_pricing_visibility",
        "sales_motion": "infer_sales_motion",
        "pricing_model": "infer_pricing_model",
        "billing_default": "infer_billing_default",
        "number_of_tiers": "infer_number_of_tiers",
        "add_ons_offered": "infer_add_ons_offered",
        "enterprise_tier_exists": "infer_enterprise_tier_exists",
        "security_compliance_gating": "infer_security_compliance_gating",
        "annual_commitment_required": "infer_annual_commitment_required",
        "plan_naming_style": "infer_plan_naming_style",
        "custom_pricing_mentioned": "infer_custom_pricing_mentioned",
        "money_back_guarantee": "infer_money_back_guarantee",
        "minimum_seats": "infer_minimum_seats",
    }
    for field_name, func_name in field_to_func.items():
        monkeypatch.setattr(
            pricing_intelligence_operations.revenueinfra,
            func_name,
            _mock_infer(
                field_name=field_name,
                status=status_by_field.get(field_name, "found"),
                value=value_by_field.get(field_name),
            ),
        )


@pytest.mark.asyncio
async def test_execute_company_derive_pricing_intelligence_noisy_context_structured(monkeypatch: pytest.MonkeyPatch):
    _mock_all_endpoints(
        monkeypatch,
        value_by_field={
            "free_trial": "yes",
            "pricing_visibility": "public",
            "sales_motion": "hybrid",
            "pricing_model": "tiered",
            "billing_default": "both_annual_emphasized",
            "number_of_tiers": "4+",
            "add_ons_offered": "yes",
            "enterprise_tier_exists": "yes",
            "security_compliance_gating": "yes",
            "annual_commitment_required": "no",
            "plan_naming_style": "generic",
            "custom_pricing_mentioned": "yes",
            "money_back_guarantee": "no",
            "minimum_seats": "not_mentioned",
        },
    )
    result = await pricing_intelligence_operations.execute_company_derive_pricing_intelligence(
        input_data={
            "cumulative_context": {
                "company_domain": "acme.com",
                "pricing_page_url": "https://acme.com/pricing",
                "company_name": "Acme Inc",
                "company_profile": {"company_domain": "ignored.com"},
                "ads": [{"headline": "noise"}],
            },
            "irrelevant": {"nested": ["values"]},
        }
    )

    assert result["operation_id"] == "company.derive.pricing_intelligence"
    assert result["status"] == "found"
    assert isinstance(result["provider_attempts"], list)
    assert len(result["provider_attempts"]) == 1
    assert result["output"]["pricing_page_url"] == "https://acme.com/pricing"
    assert result["output"]["fields_resolved"] >= 10


@pytest.mark.asyncio
async def test_execute_company_derive_pricing_intelligence_missing_pricing_page_url_failed():
    result = await pricing_intelligence_operations.execute_company_derive_pricing_intelligence(
        input_data={
            "cumulative_context": {
                "company_domain": "acme.com",
                "company_name": "Acme Inc",
            }
        }
    )

    assert result["operation_id"] == "company.derive.pricing_intelligence"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["pricing_page_url"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_derive_pricing_intelligence_partial_success_returns_found(monkeypatch: pytest.MonkeyPatch):
    _mock_all_endpoints(
        monkeypatch,
        status_by_field={
            "free_trial": "failed",
            "pricing_visibility": "failed",
            "sales_motion": "found",
            "pricing_model": "found",
            "billing_default": "failed",
            "number_of_tiers": "found",
            "add_ons_offered": "found",
            "enterprise_tier_exists": "failed",
            "security_compliance_gating": "found",
            "annual_commitment_required": "found",
            "plan_naming_style": "found",
            "custom_pricing_mentioned": "failed",
            "money_back_guarantee": "found",
            "minimum_seats": "found",
        },
        value_by_field={
            "sales_motion": "hybrid",
            "pricing_model": "tiered",
            "number_of_tiers": 4,
            "add_ons_offered": True,
            "security_compliance_gating": "yes",
            "annual_commitment_required": False,
            "plan_naming_style": "generic",
            "money_back_guarantee": "no",
            "minimum_seats": 5,
        },
    )

    result = await pricing_intelligence_operations.execute_company_derive_pricing_intelligence(
        input_data={
            "cumulative_context": {
                "company_domain": "acme.com",
                "pricing_page_url": "https://acme.com/pricing",
                "company_name": "Acme Inc",
            }
        }
    )

    assert result["status"] == "found"
    assert len(result["provider_attempts"]) == 1
    assert result["provider_attempts"][0]["provider"] == "revenueinfra"
    assert result["provider_attempts"][0]["provider_status"] == "partial"

    output = result["output"]
    assert output["pricing_page_url"] == "https://acme.com/pricing"
    assert output["sales_motion"] == "hybrid"
    assert output["number_of_tiers"] == 4
    assert output["add_ons_offered"] == "yes"
    assert output["annual_commitment_required"] == "no"
    assert output["minimum_seats"] == "5"
    assert output["free_trial"] is None
