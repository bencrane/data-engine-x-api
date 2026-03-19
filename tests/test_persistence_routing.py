"""
Tests for app/services/persistence_routing.py

All database calls are mocked — no real DB access.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.auth.models import AuthContext
from app.routers._responses import DataEnvelope
from app.routers.execute_v1 import ExecuteV1Request, _finalize_execute_response
from app.services.entity_state import EntityStateVersionError
from app.services.persistence_routing import (
    DEDICATED_TABLE_REGISTRY,
    persist_standalone_result,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_ORG_ID = "org-111"
_COMPANY_ID = "company-222"
_RUN_ID = "run-333"


def _auth() -> AuthContext:
    return AuthContext(
        user_id=None,
        org_id=_ORG_ID,
        company_id=_COMPANY_ID,
        role="org_admin",
        auth_method="api_token",
    )


def _found_result(output: dict | None = None) -> dict:
    return {
        "run_id": _RUN_ID,
        "operation_id": "company.enrich.profile",
        "status": "found",
        "output": output if output is not None else {"company_domain": "acme.com"},
        "provider_attempts": [],
    }


# ---------------------------------------------------------------------------
# Guard tests
# ---------------------------------------------------------------------------


def test_persist_standalone_result_skips_when_not_found():
    result = {
        "run_id": _RUN_ID,
        "status": "not_found",
        "output": {"company_domain": "acme.com"},
    }
    assert persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.enrich.profile",
        input_data={},
        result=result,
    ) is None


def test_persist_standalone_result_skips_when_no_output():
    result = {"run_id": _RUN_ID, "status": "found", "output": None}
    assert persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.enrich.profile",
        input_data={},
        result=result,
    ) is None


def test_persist_standalone_result_skips_when_empty_output():
    result = {"run_id": _RUN_ID, "status": "found", "output": {}}
    assert persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.enrich.profile",
        input_data={},
        result=result,
    ) is None


# ---------------------------------------------------------------------------
# Entity upsert — success paths
# ---------------------------------------------------------------------------


@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_entity_upsert_company(mock_upsert):
    mock_upsert.return_value = {"entity_id": "entity-abc"}
    output = {"company_domain": "acme.com", "company_name": "Acme Inc"}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.enrich.profile",
        input_data={},
        result=_found_result(output),
    )
    assert ret is not None
    assert ret["entity_upsert"]["status"] == "succeeded"
    assert ret["entity_upsert"]["entity_id"] == "entity-abc"
    mock_upsert.assert_called_once_with(
        org_id=_ORG_ID,
        company_id=_COMPANY_ID,
        canonical_fields=output,
        last_operation_id="company.enrich.profile",
        last_run_id=_RUN_ID,
    )


@patch("app.services.persistence_routing.upsert_person_entity")
def test_persist_standalone_result_entity_upsert_person(mock_upsert):
    mock_upsert.return_value = {"entity_id": "entity-person-xyz"}
    output = {"linkedin_url": "https://linkedin.com/in/jane", "full_name": "Jane Doe"}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="person",
        operation_id="person.enrich.profile",
        input_data={},
        result={**_found_result(output), "operation_id": "person.enrich.profile"},
    )
    assert ret["entity_upsert"]["status"] == "succeeded"
    assert ret["entity_upsert"]["entity_id"] == "entity-person-xyz"
    mock_upsert.assert_called_once()


# ---------------------------------------------------------------------------
# Entity upsert — error paths
# ---------------------------------------------------------------------------


@patch("app.services.persistence_routing.upsert_icp_job_titles")
@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_entity_upsert_version_error(mock_upsert, mock_table):
    """EntityStateVersionError → entity_upsert failed; dedicated table write still runs."""
    mock_upsert.side_effect = EntityStateVersionError("Version conflict")
    mock_table.return_value = {"rows": []}

    output = {"domain": "acme.com", "company_name": "Acme"}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.derive.icp_job_titles",
        input_data={},
        result=_found_result(output),
    )
    assert ret["entity_upsert"]["status"] == "failed"
    assert "Version conflict" in ret["entity_upsert"]["error"]
    # Dedicated table write ran independently
    mock_table.assert_called_once()


# ---------------------------------------------------------------------------
# Dedicated table writes — success paths
# ---------------------------------------------------------------------------


@patch("app.services.persistence_routing.upsert_icp_job_titles")
@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_dedicated_table_icp_job_titles(mock_upsert, mock_table):
    mock_upsert.return_value = {"entity_id": "entity-1"}
    mock_table.return_value = {"org_id": _ORG_ID}

    output = {"domain": "acme.com", "company_name": "Acme", "parallel_raw_response": {"data": 1}}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.derive.icp_job_titles",
        input_data={},
        result=_found_result(output),
    )
    assert ret["dedicated_table"]["status"] == "succeeded"
    assert ret["dedicated_table"]["table"] == "icp_job_titles"
    mock_table.assert_called_once()
    call_kwargs = mock_table.call_args.kwargs
    assert call_kwargs["company_domain"] == "acme.com"
    assert call_kwargs["raw_parallel_output"] == {"data": 1}


@patch("app.services.persistence_routing._lookup_company_entity_id")
@patch("app.services.persistence_routing.upsert_company_customers")
@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_dedicated_table_company_customers(
    mock_upsert, mock_customers, mock_lookup
):
    mock_upsert.return_value = {"entity_id": "entity-1"}
    mock_lookup.return_value = "entity-1"
    mock_customers.return_value = []

    customers = [{"customer_name": "Globex", "customer_domain": "globex.com"}]
    output = {"company_domain": "acme.com", "customers": customers}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.research.discover_customers_gemini",
        input_data={},
        result=_found_result(output),
    )
    assert ret["dedicated_table"]["status"] == "succeeded"
    mock_customers.assert_called_once()
    call_kwargs = mock_customers.call_args.kwargs
    assert call_kwargs["company_domain"] == "acme.com"
    assert call_kwargs["customers"] == customers


# ---------------------------------------------------------------------------
# No registry entry — skipped
# ---------------------------------------------------------------------------


@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_dedicated_table_no_registry(mock_upsert):
    mock_upsert.return_value = {"entity_id": "entity-1"}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.enrich.profile",  # not in registry
        input_data={},
        result=_found_result({"company_domain": "acme.com"}),
    )
    assert ret["dedicated_table"]["status"] == "skipped"
    assert ret["dedicated_table"]["reason"] == "no_registry_entry"


# ---------------------------------------------------------------------------
# Guard fails inside dedicated table writer
# ---------------------------------------------------------------------------


@patch("app.services.persistence_routing.upsert_company_ads")
@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_dedicated_table_guard_fails(mock_upsert, mock_ads):
    mock_upsert.return_value = {"entity_id": "entity-1"}
    output = {"company_domain": "acme.com", "ads": []}  # empty ads list
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.ads.search.linkedin",
        input_data={},
        result=_found_result(output),
    )
    assert ret["dedicated_table"]["status"] == "skipped"
    assert ret["dedicated_table"]["reason"] == "empty_ads_list"
    mock_ads.assert_not_called()


# ---------------------------------------------------------------------------
# input_data fallback
# ---------------------------------------------------------------------------


@patch("app.services.persistence_routing._lookup_company_entity_id")
@patch("app.services.persistence_routing.upsert_company_customers")
@patch("app.services.persistence_routing.upsert_company_entity")
def test_persist_standalone_result_input_data_fallback(
    mock_upsert, mock_customers, mock_lookup
):
    """company_domain absent from output but present in input_data → still works."""
    mock_upsert.return_value = {"entity_id": "entity-1"}
    mock_lookup.return_value = "entity-1"
    mock_customers.return_value = []

    customers = [{"customer_name": "Globex", "customer_domain": "globex.com"}]
    output = {"customers": customers}  # no domain in output
    input_data = {"company_domain": "acme.com"}
    ret = persist_standalone_result(
        auth=_auth(),
        entity_type="company",
        operation_id="company.research.discover_customers_gemini",
        input_data=input_data,
        result=_found_result(output),
    )
    assert ret["dedicated_table"]["status"] == "succeeded"
    call_kwargs = mock_customers.call_args.kwargs
    assert call_kwargs["company_domain"] == "acme.com"


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------


def test_registry_covers_all_auto_persist_operations():
    expected = {
        "company.derive.icp_job_titles",
        "company.derive.intel_briefing",
        "person.derive.intel_briefing",
        "company.research.discover_customers_gemini",
        "company.research.lookup_customers_resolved",
        "company.research.icp_job_titles_gemini",
        "company.ads.search.linkedin",
        "company.ads.search.meta",
        "company.ads.search.google",
        "person.search.sales_nav_url",
        "company.search.enigma.brands",
    }
    assert expected == set(DEDICATED_TABLE_REGISTRY.keys())


# ---------------------------------------------------------------------------
# _finalize_execute_response
# ---------------------------------------------------------------------------


@patch("app.routers.execute_v1.persist_operation_execution")
def test_finalize_execute_response_without_persist(mock_persist):
    payload = ExecuteV1Request(
        operation_id="company.enrich.profile",
        entity_type="company",
        input={"company_domain": "acme.com"},
        persist=False,
    )
    result = {"run_id": _RUN_ID, "status": "found", "output": {"company_domain": "acme.com"}}
    response = _finalize_execute_response(auth=_auth(), payload=payload, result=result)
    assert isinstance(response, DataEnvelope)
    assert "persistence" not in response.data
    mock_persist.assert_called_once()


@patch("app.services.persistence_routing.upsert_company_entity")
@patch("app.routers.execute_v1.persist_operation_execution")
def test_finalize_execute_response_with_persist(mock_persist, mock_upsert):
    mock_upsert.return_value = {"entity_id": "entity-1"}
    payload = ExecuteV1Request(
        operation_id="company.enrich.profile",
        entity_type="company",
        input={"company_domain": "acme.com"},
        persist=True,
    )
    result = {"run_id": _RUN_ID, "status": "found", "output": {"company_domain": "acme.com"}}
    response = _finalize_execute_response(auth=_auth(), payload=payload, result=result)
    assert isinstance(response, DataEnvelope)
    assert "persistence" in response.data
    assert "entity_upsert" in response.data["persistence"]
    assert "dedicated_table" in response.data["persistence"]
