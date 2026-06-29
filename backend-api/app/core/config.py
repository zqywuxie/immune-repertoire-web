"""Application configuration loaded from environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "API_", "env_file": ".env", "extra": "ignore"}

    debug: bool = False
    database_url: str = "mysql+pymysql://root:@127.0.0.1:3306/immune_repertoire"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
