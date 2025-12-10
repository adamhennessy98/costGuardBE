from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    app_name: str = "CostGuard API"
    debug: bool = False
    database_url: str = "sqlite:///./costguard.db"
    invoice_storage_dir: str = "storage/invoices"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Ensure settings are constructed once per process."""

    return Settings()
