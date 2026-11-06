"""All settings come from env vars. Nothing is read from files, no secrets are logged."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _agents_root() -> Path:
    return Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_agents_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    core_api_url: str = "https://giving-api.onrender.com"
    internal_token: str = ""
    # The live API currently rejects INTERNAL_TOKEN ("Invalid token"). Until Person 1 fixes it,
    # FAKE_CORE=true serves canned MCP results so the agents are runnable end to end.
    fake_core: bool = False

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    mcp_server_path: str = "../mcp-server/server.py"

    # Any mutating MCP call returns a canned result instead of hitting the API.
    # Defaults to True: shipping money-moving code must require an explicit opt-in.
    dry_run: bool = True

    web_origin: str = "http://localhost:3000"

    # Chat rate limit, per client per minute. Every request counts, including rejected ones.
    rate_limit_per_min: int = 30

    # Off by default: the scheduler must be opted into explicitly.
    scheduler_enabled: bool = False

    giving_interval_hours: int = 720
    watchdog_interval_seconds: int = 300
    milestone_interval_seconds: int = 600

    @property
    def mcp_server_file(self) -> Path:
        p = Path(self.mcp_server_path)
        return p if p.is_absolute() else (_agents_root() / p).resolve()


@lru_cache
def settings() -> Settings:
    return Settings()
