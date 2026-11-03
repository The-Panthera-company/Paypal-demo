from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_webhook_id: str = ""

    database_url: str = ""

    currency: str = "USD"
    min_donation_cents: int = 100
    max_donation_cents: int = 100_000

    cors_origins: str = "http://localhost:3000"

    # Bearer tokens: agents call /internal/*, the admin console calls /admin/*.
    internal_token: str = ""
    admin_token: str = ""

    # Routes not built yet return their spec example (header X-Stub) instead of 501.
    stub_examples: bool = True

    # How often the open round's projected match is recomputed; 0 turns the background loop off.
    projection_interval_seconds: int = 300

    # Milestone tranches (including their match) up to this many cents release without an admin.
    milestone_auto_release_cents: int = 50_000

    @property
    def db_url(self) -> str:
        url = self.database_url or "sqlite:///./giving.db"
        # Render hands out postgres:// URLs; SQLAlchemy needs the driver named.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgres://")
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
