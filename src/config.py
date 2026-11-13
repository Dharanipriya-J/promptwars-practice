"""
PitchPulse 2026 - Centralised Application Configuration
Uses pydantic-settings to manage environment variables with strong type contracts.
"""

import logging
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("pitchpulse.config")

MIN_TOKEN_LENGTH = 16


class Settings(BaseSettings):
    gemini_api_key: str | None = None
    staff_secret_token: str = ""
    allowed_origin: str = "http://localhost:8000"
    environment: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    def validate_on_startup(self) -> None:
        """
        Called once at application startup to enforce critical runtime requirements.
        In production: refuses to start without a sufficiently long staff secret token.
        In development: logs a critical warning but continues.
        """
        if not self.staff_secret_token:
            msg = (
                "STAFF_SECRET_TOKEN is not set. Incident dispatch endpoint will return 503 until a token is configured."
            )
            if self.environment == "production":
                logger.critical(msg)
                sys.exit(1)
            else:
                logger.warning(
                    "Development mode: %s Set STAFF_SECRET_TOKEN in .env to enable incident dispatch.",
                    msg,
                )
        elif len(self.staff_secret_token) < MIN_TOKEN_LENGTH:
            msg = (
                f"STAFF_SECRET_TOKEN is too short (minimum {MIN_TOKEN_LENGTH} characters). "
                "Use a randomly generated secret for security."
            )
            if self.environment == "production":
                logger.critical(msg)
                sys.exit(1)
            else:
                logger.warning("Development mode: %s", msg)
        else:
            logger.info("Staff secret token configured (%d chars).", len(self.staff_secret_token))


settings = Settings()
