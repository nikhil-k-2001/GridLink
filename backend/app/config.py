"""Application settings. All secrets come from the environment, never from the database."""
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # DATABASE_URL (Neon via the Vercel Marketplace) or POSTGRES_URL; postgres:// URLs are normalised for psycopg 3.
    database_url: str = Field(default="postgresql+psycopg://gridlink:gridlink@localhost:5434/gridlink",
                              validation_alias=AliasChoices("DATABASE_URL", "POSTGRES_URL", "database_url"))
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    # Also allow the deployed web app (production + preview URLs on Vercel).
    cors_origin_regex: str | None = r"https://gridlink-web[a-z0-9-]*\.vercel\.app"

    # Serverless deployment: create tables and load the demo workspace on first start.
    auto_setup: bool = False
    # Vercel Cron sends "Authorization: Bearer $CRON_SECRET" to /cron/daily-sync.
    cron_secret: str | None = None
    # Hosts that refer to this API itself (the simulated DSO platforms live under /simulated/ here).
    vercel_url: str | None = None
    vercel_project_production_url: str | None = None

    # ENTSO-E: user-supplied token only. GridLink never ships or fabricates credentials.
    entsoe_api_token: str | None = Field(default=None)
    entsoe_base_url: str = "https://web-api.tp.entsoe.eu/api"

    smard_download_url: str = "https://www.smard.de/nip-download-manager/nip/download/market-data"

    # Optional AI assistance (Gemini Developer API free tier). Core pipeline never depends on it.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    # Optional background sync. Manual sync is the default workflow.
    scheduler_enabled: bool = False

    # API test bench: only these hosts may be called (prevents the server being used to probe internal networks).
    api_test_allowed_hosts: list[str] = [
        "www.smard.de", "smard.de", "web-api.tp.entsoe.eu", "www.marktstammdatenregister.de",
        "marktstammdatenregister.de", "datahub-enedis.fr", "api.energidataservice.dk", "data.elexon.co.uk",
    ]

    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    http_backoff_base_seconds: float = 1.0
    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def _psycopg_scheme(cls, v: str) -> str:
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @property
    def self_hosts(self) -> set[str]:
        return {h for h in (self.vercel_url, self.vercel_project_production_url) if h}


@lru_cache
def get_settings() -> Settings:
    return Settings()
