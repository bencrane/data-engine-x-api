from __future__ import annotations

import pytest

from app.routers.registry_v1 import RegistryOperationsRequest, list_registry_operations
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
