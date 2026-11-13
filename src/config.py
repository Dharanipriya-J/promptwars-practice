"""
PitchPulse 2026 - Centralised Application Configuration
Uses pydantic-settings to manage environment variables with strong type contracts.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str | None = None
    staff_secret_token: str = "fifa-staff-secure-2026"
    allowed_origin: str = "http://localhost:8000"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
