"""Runtime configuration, loaded once from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    workers: int = Field(default=1)

    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    # Single-process deploy: directory of the built static client to serve from
    # the same origin as the API. Empty -> auto-detect repo-root/client/build.
    client_dir: str = Field(default="", alias="CLIENT_DIR")

    # Extraction tuning
    max_formats: int = Field(default=40, ge=1, le=200)
    request_timeout: int = Field(default=90, ge=5)
    max_retries: int = Field(default=2, ge=0)
    scrape_max_bytes: int = Field(default=50_000, ge=1_000)

    # Browser impersonation (curl_cffi): mimics a real browser's TLS/HTTP
    # fingerprint so anti-bot sites ( tiktok, …) stop
    # answering with 403/410. No-op if curl_cffi isn't installed.
    enable_impersonation: bool = Field(default=True)
    impersonate_client: str = Field(default="chrome")

    # Validate extracted format URLs with a quick probe (same impersonation +
    # headers the proxy uses) and drop only the ones that are *confirmed* dead
    # (4xx/5xx or an HTML error page). Uncertain probes (timeout/network) keep
    # the format — better to show a maybe-working link than hide a working one.
    validate_formats: bool = Field(default=True)
    validate_timeout: int = Field(default=6, ge=1)  # per-probe, seconds
    validate_concurrency: int = Field(default=10, ge=1, le=50)

    # Thread pool for blocking yt-dlp work
    extract_workers: int = Field(default=4, ge=1, le=32)

    # In-memory result cache
    cache_ttl: int = Field(default=300, ge=0)
    cache_max_entries: int = Field(default=512, ge=0)

    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()] or ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
