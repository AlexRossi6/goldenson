from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GoldenSon API"
    api_prefix: str = "/api"
    database_url: str = "sqlite+aiosqlite:///./goldenson.db"
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    storage_root: Path = Path("~/.goldenson/files").expanduser()
    max_upload_size: int = 100 * 1024 * 1024

    model_config = SettingsConfigDict(env_prefix="GOLDENSON_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
