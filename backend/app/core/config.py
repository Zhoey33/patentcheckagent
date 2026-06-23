"""这个文件用于集中读取后端环境变量和运行时配置。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_secret_key: str = Field(default="change-me-in-production", min_length=8)
    frontend_url: str = "http://localhost:3000"

    database_url: str = "sqlite:///./patent_check_agent.sqlite3"
    redis_url: str = "redis://localhost:6379/0"

    gpt_base_url: str = "https://helloapi.cc"
    gpt_api_key: str = ""
    gpt_model: str = "gpt-5.5"
    gpt_timeout_seconds: int = 180
    gpt_max_retries: int = 2

    max_file_size_mb: int = 20
    max_task_files: int = 4
    max_total_text_chars: int = 200_000
    upload_dir: Path = Path("uploads")
    enable_worker_queue: bool = True

    access_token_expire_minutes: int = 60 * 12

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @field_validator("upload_dir", mode="before")
    @classmethod
    def normalize_upload_dir(cls, value: str | Path) -> Path:
        return Path(value)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
