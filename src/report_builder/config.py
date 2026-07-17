from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def parse_csv(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    app_name: str = "TURKUAZ Report Builder"
    app_environment: str = "local"
    database_url: str = "sqlite:///./data/report_builder.db"
    auto_create_schema: bool = False
    backend_cors_origins: Annotated[list[str], NoDecode, BeforeValidator(parse_csv)] = [
        "http://localhost:7505",
        "http://127.0.0.1:7505",
    ]
    backend_cors_origin_regex: str | None = r"https?://[^/]+:7505"
    auth_enabled: bool = True
    identity_secret_key: str = "dev-change-me-32-byte-secret-key-for-turkuaz-identity"
    identity_algorithm: str = "HS256"
    report_source_encryption_key: str | None = None
    query_timeout_seconds: int = 20
    preview_row_limit: int = 200
    absolute_row_limit: int = 50_000
    max_concurrent_queries: int = 4

    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
