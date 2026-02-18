# app/config.py — Pydantic settings (env vars)

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Public API URL (used by Trigger callbacks / local tooling)
    api_url: str | None = None

    # Postgres
    database_url: str

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Trigger.dev
    trigger_secret_key: str
    trigger_project_id: str
    trigger_api_url: str = "https://api.trigger.dev"

    # Auth
    jwt_secret: str
    super_admin_jwt_secret: str
    super_admin_api_key: str | None = None
    internal_api_key: str

    # Provider keys and operation runtime settings (email operations v1)
    icypeas_api_key: str | None = None
    leadmagic_api_key: str | None = None
    millionverifier_api_key: str | None = None
    reoon_api_key: str | None = None
    parallel_api_key: str | None = None
    prospeo_api_key: str | None = None
    ampleleads_api_key: str | None = None
    blitzapi_api_key: str | None = None
    companyenrich_api_key: str | None = None
    storeleads_api_key: str | None = None
    enigma_api_key: str | None = None
    adyntel_api_key: str | None = None
    adyntel_account_email: str | None = None
    revenueinfra_api_url: str = "https://api.revenueinfra.com"
    revenueinfra_api_key: str | None = None
    parallel_processor: str = "core"
    icypeas_poll_interval_ms: int = 2000
    icypeas_max_wait_ms: int = 45000
    millionverifier_timeout_seconds: int = 10
    reoon_mode: str = "power"
    company_enrich_profile_order: str = "prospeo,blitzapi,companyenrich,leadmagic"
    company_search_order: str = "prospeo,blitzapi,companyenrich"
    person_search_order: str = "prospeo,blitzapi,companyenrich"
    person_resolve_mobile_order: str = "leadmagic,blitzapi"
    adyntel_timeout_seconds: int = 90
    llm_primary_model: str = "gemini"
    llm_fallback_model: str = "gpt-4"
    gemini_api_key: str | None = None
    openai_api_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @field_validator("internal_api_key")
    @classmethod
    def _validate_internal_api_key(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("INTERNAL_API_KEY must be set and non-empty")
        return cleaned


@lru_cache
def get_settings() -> Settings:
    return Settings()
