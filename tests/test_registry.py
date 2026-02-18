from __future__ import annotations

from app.registry.loader import (
    get_all_operations,
    get_operation,
    get_operations_that_produce,
)
from app.routers.execute_v1 import SUPPORTED_OPERATION_IDS


def test_registry_loads_supported_operations():
    operations = get_all_operations()
    operation_ids = {op["operation_id"] for op in operations}
    assert len(operations) == len(SUPPORTED_OPERATION_IDS)
    assert operation_ids == SUPPORTED_OPERATION_IDS


def test_get_operation_by_id_returns_metadata():
    operation = get_operation("company.enrich.profile")
    assert operation is not None
    assert operation["entity_type"] == "company"
    assert operation["category"] == "enrich"
    assert "industry_primary" in operation["produces"]


def test_get_operations_that_produce_email():
    operations = get_operations_that_produce("email")
    operation_ids = {op["operation_id"] for op in operations}
    assert "person.contact.resolve_email" in operation_ids
    assert "person.enrich.profile" in operation_ids
