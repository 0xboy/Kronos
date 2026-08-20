"""Typed app settings (Alpaca paper trading) via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from config.paths import REPO_ROOT


class Settings(BaseSettings):
    """Loaded from process env and optional repo-root ``.env``."""

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    api_key: str = Field(default="", validation_alias="ALPACA_API_KEY")
    secret_key: str = Field(default="", validation_alias="ALPACA_SECRET_KEY")
    paper: bool = Field(default=True, validation_alias="ALPACA_PAPER")

    @field_validator("api_key", "secret_key", mode="before")
    @classmethod
    def _strip_str(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance (invalidate via ``get_settings.cache_clear()``)."""
    return Settings()


def load_settings() -> Settings:
    """Compatibility wrapper used by CLIs."""
    return get_settings()
