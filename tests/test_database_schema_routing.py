from __future__ import annotations

from app import database


class _SchemaClientStub:
    def __init__(self, schema_name: str):
        self.schema_name = schema_name

    def table(self, table_name: str):
        return {"schema": self.schema_name, "table": table_name}


class _RawClientStub:
    def __init__(self):
        self.schema_calls: list[str] = []

    def schema(self, schema_name: str):
        self.schema_calls.append(schema_name)
        return _SchemaClientStub(schema_name)

    def table(self, table_name: str):
        return {"schema": None, "table": table_name}


def test_schema_aware_client_routes_ops_tables():
    client = database.SchemaAwareSupabaseClient(_RawClientStub())

    result = client.table("submissions")

    assert result == {"schema": database.OPS_SCHEMA, "table": "submissions"}

    config_result = client.table("company_blueprint_configs")
    assert config_result == {"schema": database.OPS_SCHEMA, "table": "company_blueprint_configs"}

    schedule_result = client.table("company_blueprint_schedules")
    assert schedule_result == {"schema": database.OPS_SCHEMA, "table": "company_blueprint_schedules"}

    schedule_run_result = client.table("company_blueprint_schedule_runs")
    assert schedule_run_result == {"schema": database.OPS_SCHEMA, "table": "company_blueprint_schedule_runs"}

    association_result = client.table("company_entity_associations")
    assert association_result == {"schema": database.OPS_SCHEMA, "table": "company_entity_associations"}


def test_schema_aware_client_routes_entities_tables():
    client = database.SchemaAwareSupabaseClient(_RawClientStub())

    result = client.table("company_entities")

    assert result == {"schema": database.ENTITIES_SCHEMA, "table": "company_entities"}


def test_schema_aware_client_leaves_unknown_tables_unqualified():
    client = database.SchemaAwareSupabaseClient(_RawClientStub())

    result = client.table("some_other_table")

    assert result == {"schema": None, "table": "some_other_table"}
