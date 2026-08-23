from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "GoldenSon API"
    api_prefix: str = "/api"
    database_url: str = "sqlite+aiosqlite:///./goldenson.db"
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    storage_root: Path = Path("~/.goldenson/files").expanduser()
    max_upload_size: int = 100 * 1024 * 1024
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_runtime_root: Path = Path("~/.goldenson/runtime").expanduser()
    embedding_model: str = ""
    embedding_provider_version: str = "ollama-api-v1"
    agent_max_tool_calls: int = 8
    agent_max_run_seconds: float = 60.0
    agent_provider_timeout_seconds: float = 45.0
    agent_tool_timeout_seconds: float = 10.0

    @field_validator("ollama_base_url")
    @classmethod
    def validate_local_llm_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Ollama endpoint must be a local loopback HTTP URL")
        return value.rstrip("/")

    model_config = SettingsConfigDict(env_prefix="GOLDENSON_", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
