from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    app_name: str = "CostGuard API"
    debug: bool = False
    database_url: str = "sqlite:///./costguard.db"
    invoice_storage_dir: str = "storage/invoices"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_database_url(self) -> str:
        """Return the database URL with the correct driver prefix.

        Supabase provides connection strings starting with ``postgresql://``.
        SQLAlchemy 2.x requires the psycopg (v3) driver to be specified
        explicitly as ``postgresql+psycopg://``.

        This property handles the conversion automatically so users can
        paste their Supabase connection string as-is.
        """
        url = self.database_url
        # Convert bare postgresql:// → postgresql+psycopg:// for psycopg v3
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Ensure settings are constructed once per process."""

    return Settings()
