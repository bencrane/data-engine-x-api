# app/config.py — Pydantic settings (env vars)

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_role_key: str

    # Trigger.dev
    trigger_secret_key: str
    trigger_api_url: str = "https://api.trigger.dev"

    # Auth
    jwt_secret: str
    internal_api_key: str

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
