# app/database.py — Supabase client

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

from app.config import get_settings

OPS_SCHEMA = "ops"
ENTITIES_SCHEMA = "entities"

OPS_TABLES = frozenset(
    {
        "orgs",
        "companies",
        "users",
        "api_tokens",
        "super_admins",
        "steps",
        "blueprints",
        "blueprint_steps",
        "submissions",
        "pipeline_runs",
        "step_results",
        "operation_runs",
        "operation_attempts",
    }
)

ENTITIES_TABLES = frozenset(
    {
        "company_entities",
        "person_entities",
        "job_posting_entities",
        "entity_timeline",
        "entity_snapshots",
        "entity_relationships",
        "icp_job_titles",
        "extracted_icp_job_title_details",
        "company_intel_briefings",
        "person_intel_briefings",
        "gemini_icp_job_titles",
        "company_customers",
        "company_ads",
        "salesnav_prospects",
    }
)

TABLE_TO_SCHEMA: Mapping[str, str] = {
    **{table_name: OPS_SCHEMA for table_name in OPS_TABLES},
    **{table_name: ENTITIES_SCHEMA for table_name in ENTITIES_TABLES},
}


class SchemaAwareSupabaseClient:
    """
    Route moved application tables to explicit PostgREST schemas.

    This keeps table access paths explicit without requiring every caller to
    manually thread schema selection through each query chain.
    """

    def __init__(self, client: Client):
        self._client = client

    def table(self, table_name: str):
        schema_name = TABLE_TO_SCHEMA.get(table_name)
        if schema_name is None:
            return self._client.table(table_name)
        return self._client.schema(schema_name).table(table_name)

    def schema(self, schema_name: str):
        return self._client.schema(schema_name)

    def __getattr__(self, attr_name: str) -> Any:
        return getattr(self._client, attr_name)


@lru_cache
def _get_raw_supabase_client() -> Client:
    settings = get_settings()
    return create_client(
        settings.supabase_url,
        settings.supabase_service_key,
    )


@lru_cache
def get_supabase_client() -> SchemaAwareSupabaseClient:
    return SchemaAwareSupabaseClient(_get_raw_supabase_client())


def get_schema_client(schema_name: str):
    return _get_raw_supabase_client().schema(schema_name)


def get_ops_client():
    return get_schema_client(OPS_SCHEMA)


def get_entities_client():
    return get_schema_client(ENTITIES_SCHEMA)
