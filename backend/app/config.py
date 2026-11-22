"""Application settings. All secrets come from the environment, never from the database."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://gridlink:gridlink@localhost:5434/gridlink"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
