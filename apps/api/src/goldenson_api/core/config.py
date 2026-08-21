from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GoldenSon API"
    api_prefix: str = "/api"
    database_url: str = "sqlite+aiosqlite:///./goldenson.db"

    model_config = SettingsConfigDict(env_prefix="GOLDENSON_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
