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
    scrape_max_bytes: int = Field(default=200_000, ge=1_000)

    # ----- Authentication / anti-block -----------------------------------
    # Server-side default cookies (Netscape cookies.txt path). Unlocks
    # age-restricted / private / login-gated content (YouTube, Instagram, …)
    # and tames "sign in to confirm you're not a bot" on datacenter IPs. Used
    # only when the request carries no per-user cookies of its own. Empty = off.
    cookie_file: str = Field(default="", alias="COOKIE_FILE")
    # Hard cap on the per-request cookie blob the client may paste (bytes).
    max_cookie_bytes: int = Field(default=262_144, ge=0)

    # Outbound proxy (http/https/socks5) for extraction, link probing AND the
    # media proxy — routes around datacenter-IP blocks and rate limits. e.g.
    # "http://user:pass@host:port" or "socks5://host:port". Empty = direct.
    proxy_url: str = Field(default="", alias="PROXY_URL")

    # YouTube player clients to try, comma-separated (maps to
    # extractor_args youtube:player_client). Empty = yt-dlp's default (full
    # quality ladder). Pinning a single mobile client collapses YouTube to
    # 360p, so prefer a list that keeps "default", e.g.
    # "default,tv,web_safari". "tv_embedded"/"mweb" help with age-gates.
    youtube_player_clients: str = Field(default="", alias="YOUTUBE_PLAYER_CLIENTS")
    # Optional PO token(s) for YouTube (maps to extractor_args youtube:po_token),
    # comma-separated "CLIENT.CONTEXT+TOKEN" values. Lets a datacenter IP pass
    # bot-detection. Usually supplied by a bgutil PO-token provider sidecar.
    youtube_po_token: str = Field(default="", alias="YOUTUBE_PO_TOKEN")

    # Politeness: random sleep (seconds) between extractor HTTP requests. A
    # small value (1–3) markedly cuts 429/"used too much" blocks under load.
    sleep_requests: float = Field(default=0.0, ge=0, alias="SLEEP_REQUESTS")

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

    # ----- Auto-generated subtitles (Groq Whisper speech-to-text) ---------
    # Transcription only -- speech becomes text in whatever language it was
    # spoken, no translation direction involved. Free at console.groq.com,
    # no card required. Empty key disables /transcribe (503 instead of
    # failing mid-pipeline).
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    transcribe_enabled: bool = Field(default=True)
    # Concurrent transcription jobs across all clients — each one pins a
    # Groq-rate-limited pipeline plus local ffmpeg CPU work.
    transcribe_max_concurrent_jobs: int = Field(default=2, ge=1, le=10)
    # Hard cap on the one audio/video stream a job downloads to disk (the
    # only place in the app that writes media bytes to disk).
    transcribe_max_download_bytes: int = Field(default=300_000_000, ge=1_000_000)
    # Only chunk the audio when it would exceed Groq's per-request limits.
    transcribe_chunk_seconds: int = Field(default=600, ge=60)
    # How long a finished/errored job's result stays available for polling
    # and subtitle-file downloads before it's swept from memory.
    transcribe_job_ttl: int = Field(default=1800, ge=60)
    # Thread/subprocess pool size for ffmpeg extraction/chunking.
    transcribe_workers: int = Field(default=2, ge=1, le=8)
    groq_whisper_model: str = Field(default="whisper-large-v3-turbo")

    # ----- Image/gallery extraction (gallery-dl) ---------------------------
    gallery_dl_timeout: int = Field(default=45, ge=5)
    gallery_dl_workers: int = Field(default=3, ge=1, le=20)
    gallery_dl_binary: str = Field(default="gallery-dl")

    # ----- ffmpeg/ffprobe (transcription pipeline only) --------------------
    # Bare names rely on the running process's PATH, which is NOT always the
    # same PATH an interactive shell sees (systemd services, some containers,
    # or a dev machine where ffmpeg was only added to a shell profile). Point
    # these at an absolute path if `/health` reports either as unavailable.
    ffmpeg_binary: str = Field(default="ffmpeg", alias="FFMPEG_BINARY")
    ffprobe_binary: str = Field(default="ffprobe", alias="FFPROBE_BINARY")

    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()] or ["*"]

    @property
    def youtube_player_client_list(self) -> list[str]:
        return [c.strip() for c in self.youtube_player_clients.split(",") if c.strip()]

    @property
    def youtube_po_token_list(self) -> list[str]:
        return [t.strip() for t in self.youtube_po_token.split(",") if t.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
