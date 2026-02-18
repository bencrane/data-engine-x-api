from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.routers import registry_v1
from app.routers.registry_v1 import (
    RegistryOperationsRequest,
    _extract_fields_and_options_from_prompt,
    list_registry_operations,
)
from app.services.blueprint_assembler import assemble_blueprint


def _operation_ids(assembled: dict) -> list[str]:
    return [step["operation_id"] for step in assembled["steps"]]


def test_simple_company_enrichment_blueprint():
    assembled = assemble_blueprint(
        desired_fields=["company_name", "industry_primary"],
        entity_type="company",
        options=None,
    )
    assert _operation_ids(assembled) == ["company.enrich.profile"]
    assert assembled["unresolvable_fields"] == []


def test_company_research_blueprint_order():
    assembled = assemble_blueprint(
        desired_fields=["company_name", "g2_url", "pricing_page_url"],
        entity_type="company",
        options=None,
    )
    assert _operation_ids(assembled) == [
        "company.enrich.profile",
        "company.research.resolve_g2_url",
        "company.research.resolve_pricing_page_url",
    ]
    assert assembled["unresolvable_fields"] == []


def test_cross_entity_company_to_person_fan_out():
    assembled = assemble_blueprint(
        desired_fields=["company_name", "email"],
        entity_type="company",
        options=None,
    )
    assert _operation_ids(assembled) == [
        "company.enrich.profile",
        "person.search",
        "person.contact.resolve_email",
    ]
    fan_out_step = assembled["steps"][1]
    assert fan_out_step["operation_id"] == "person.search"
    assert fan_out_step.get("fan_out") is True


def test_pricing_intelligence_condition_added():
    assembled = assemble_blueprint(
        desired_fields=["company_name"],
        entity_type="company",
        options={"include_pricing_intelligence": True},
    )
    operation_ids = _operation_ids(assembled)
    assert operation_ids == [
        "company.enrich.profile",
        "company.research.resolve_pricing_page_url",
        "company.derive.pricing_intelligence",
    ]
    pricing_step = assembled["steps"][-1]
    assert pricing_step["operation_id"] == "company.derive.pricing_intelligence"
    assert pricing_step["step_config"]["condition"] == {"field": "pricing_page_url", "op": "exists"}


def test_unresolvable_field_is_reported():
    assembled = assemble_blueprint(
        desired_fields=["not_a_real_output_field"],
        entity_type="company",
        options=None,
    )
    assert assembled["steps"] == []
    assert assembled["unresolvable_fields"] == ["not_a_real_output_field"]


def _mock_nl_extraction(monkeypatch: pytest.MonkeyPatch, mapped: dict) -> None:
    monkeypatch.setattr(
        registry_v1,
        "get_settings",
        lambda: SimpleNamespace(
            anthropic_api_key="test-anthropic",
            openai_api_key="test-openai",
            gemini_api_key="test-gemini",
            llm_primary_model="test-primary",
            llm_fallback_model="test-fallback",
        ),
    )

    async def _anthropic_stub(**_: object) -> dict:
        return {"mapped": mapped}

    async def _unused_stub(**_: object) -> dict:
        raise AssertionError("Fallback LLM provider should not be called when Anthropic returns mapped output")

    monkeypatch.setattr(registry_v1.anthropic_provider, "resolve_structured", _anthropic_stub)
    monkeypatch.setattr(registry_v1.openai_provider, "resolve_structured", _unused_stub)
    monkeypatch.setattr(registry_v1.gemini, "resolve_structured", _unused_stub)


@pytest.mark.asyncio
async def test_nl_prompt_find_vps_get_emails_triggers_person_search_chain(monkeypatch: pytest.MonkeyPatch):
    _mock_nl_extraction(
        monkeypatch,
        {
            "desired_fields": ["current_title"],
            "options": {"job_title": "VP"},
        },
    )
    desired_fields, options = await _extract_fields_and_options_from_prompt(
        prompt="find VPs and get their emails",
        entity_type="company",
    )
    assert "email" in desired_fields
    assembled = assemble_blueprint(
        desired_fields=desired_fields,
        entity_type="company",
        options=options,
    )
    operation_ids = _operation_ids(assembled)
    assert "person.search" in operation_ids
    assert "person.contact.resolve_email" in operation_ids
    person_search_step = next(step for step in assembled["steps"] if step["operation_id"] == "person.search")
    assert person_search_step.get("fan_out") is True


@pytest.mark.asyncio
async def test_nl_prompt_profile_and_employee_count_prefers_company_profile(monkeypatch: pytest.MonkeyPatch):
    _mock_nl_extraction(
        monkeypatch,
        {
            "desired_fields": ["company_name", "employee_count"],
            "options": {},
        },
    )
    desired_fields, options = await _extract_fields_and_options_from_prompt(
        prompt="enrich companies with profile and employee count",
        entity_type="company",
    )
    assembled = assemble_blueprint(
        desired_fields=desired_fields,
        entity_type="company",
        options=options,
    )
    assert _operation_ids(assembled) == ["company.enrich.profile"]


@pytest.mark.asyncio
async def test_nl_prompt_shopify_plan_includes_ecommerce(monkeypatch: pytest.MonkeyPatch):
    _mock_nl_extraction(
        monkeypatch,
        {
            "desired_fields": ["ecommerce_platform", "ecommerce_plan"],
            "options": {},
        },
    )
    desired_fields, options = await _extract_fields_and_options_from_prompt(
        prompt="get ecommerce store data including Shopify plan",
        entity_type="company",
    )
    assembled = assemble_blueprint(
        desired_fields=desired_fields,
        entity_type="company",
        options=options,
    )
    assert "company.enrich.ecommerce" in _operation_ids(assembled)


def test_fields_mode_employee_count_and_company_name_uses_profile_only():
    assembled = assemble_blueprint(
        desired_fields=["employee_count", "company_name"],
        entity_type="company",
        options=None,
    )
    assert _operation_ids(assembled) == ["company.enrich.profile"]


def test_fields_mode_employee_count_and_ecommerce_platform_uses_profile_and_ecommerce():
    assembled = assemble_blueprint(
        desired_fields=["employee_count", "ecommerce_platform"],
        entity_type="company",
        options=None,
    )
    operation_ids = _operation_ids(assembled)
    assert "company.enrich.profile" in operation_ids
    assert "company.enrich.ecommerce" in operation_ids


@pytest.mark.asyncio
async def test_post_processing_adds_email_when_job_title_without_contact_fields(monkeypatch: pytest.MonkeyPatch):
    _mock_nl_extraction(
        monkeypatch,
        {
            "desired_fields": ["current_title", "seniority"],
            "options": {"job_title": "Director"},
        },
    )
    desired_fields, _ = await _extract_fields_and_options_from_prompt(
        prompt="find directors at these companies",
        entity_type="company",
    )
    assert "email" in desired_fields


@pytest.mark.asyncio
async def test_registry_query_by_entity_type():
    response = await list_registry_operations(RegistryOperationsRequest(entity_type="person"))
    operations = response.data["operations"]
    assert operations
    assert all(op["entity_type"] == "person" for op in operations)


@pytest.mark.asyncio
async def test_registry_query_by_produces_field():
    response = await list_registry_operations(RegistryOperationsRequest(produces_field="email"))
    operation_ids = {op["operation_id"] for op in response.data["operations"]}
    assert "person.contact.resolve_email" in operation_ids
    assert "person.enrich.profile" in operation_ids
