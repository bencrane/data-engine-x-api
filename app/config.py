# app/config.py — Pydantic settings (env vars)

from functools import lru_cache

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
    internal_api_key: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DATA_ENGINE_",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
