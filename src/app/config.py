"""
Application configuration for Polla del Mundial.

Settings are loaded with the following priority (highest to lowest):
  1. Environment variables (e.g. DATABASE_URL=...)
  2. A .env file in the project root (loaded by pydantic-settings or python-dotenv)
  3. Hard-coded defaults defined below

Usage:
    from app.config import settings
    print(settings.DATABASE_URL)
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Try to use pydantic-settings (preferred); fall back to a plain class.
# ---------------------------------------------------------------------------

try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        """
        Application settings sourced from environment variables / .env file.

        All fields have sensible development defaults so the application can
        start without any external configuration.
        """

        DATABASE_URL: str = "sqlite:///world_cup.db"
        SECRET_KEY: str = "dev-secret-change-in-production"
        SESSION_DURATION_HOURS: int = 24
        DEBUG: bool = False

        # Admin username — users with this exact username gain admin privileges.
        ADMIN_USERNAME: str = "admin"

        model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

except ImportError:
    # pydantic-settings is not installed; use a simple class that reads from
    # environment variables with the same defaults.

    class Settings:  # type: ignore[no-redef]
        """Fallback settings class (no pydantic-settings installed)."""

        DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///world_cup.db")
        SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")
        SESSION_DURATION_HOURS: int = int(os.getenv("SESSION_DURATION_HOURS", "24"))
        DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")

        def __repr__(self) -> str:
            return (
                f"Settings(DATABASE_URL={self.DATABASE_URL!r}, "
                f"DEBUG={self.DEBUG!r})"
            )


# ---------------------------------------------------------------------------
# Singleton — import and use `settings` everywhere.
# ---------------------------------------------------------------------------

settings = Settings()
