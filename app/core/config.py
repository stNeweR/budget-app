from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Family Budget"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://family:family@localhost:5432/family"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+asyncpg://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+asyncpg://" + value[len("postgresql://") :]
        return value

    jwt_secret: str = "change-me-to-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    login_code_ttl_seconds: int = 300

    panel_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    telegram_bot_token: str = ""
    telegram_webhook_url: str = ""
    telegram_webhook_secret: str = ""
    telegram_webhook_path: str = "/telegram/webhook"
    telegram_api_base_url: str = "https://api.telegram.org"

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model: str = "openrouter/free"
    llm_http_referer: str = ""
    llm_title: str = "Family Budget"
    llm_timeout_seconds: float = 60.0

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token)

    @property
    def telegram_webhook_mode(self) -> bool:
        return self.telegram_enabled and bool(self.telegram_webhook_url)

    @property
    def panel_url_normalized(self) -> str:
        return self.panel_url.rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
