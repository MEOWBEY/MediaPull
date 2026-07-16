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
    # May hold SEVERAL comma-separated paths (e.g. two Instagram accounts) --
    # extraction rotates round-robin across them, and a file whose account is
    # rate-limited / bot-flagged goes on cooldown while the others keep serving.
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
    # Base URL of the bgutil PO-token provider sidecar (see the VPS installer).
    # yt-dlp's bgutil HTTP plugin auto-detects http://127.0.0.1:4416, so this
    # only needs setting when the provider runs on a NON-default port (e.g. 4416
    # was already taken). Maps to extractor_args youtubepot-bgutilhttp:base_url.
    youtube_pot_base_url: str = Field(default="", alias="YOUTUBE_POT_BASE_URL")

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
    # Cap how many unique format URLs get a live probe (top by resolution/tbr).
    # Unprobed formats stay in the list — same as an "uncertain" probe.
    validate_max_formats: int = Field(default=8, ge=1, le=200, alias="VALIDATE_MAX_FORMATS")

    # Thread pool for blocking yt-dlp work
    extract_workers: int = Field(default=4, ge=1, le=32)

    # In-memory result cache
    cache_ttl: int = Field(default=300, ge=0)
    cache_max_entries: int = Field(default=512, ge=0)

    # Admission control (single-worker public deploys)
    extract_max_in_flight: int = Field(default=8, ge=1, le=64, alias="EXTRACT_MAX_IN_FLIGHT")
    transcribe_max_jobs_stored: int = Field(
        default=64, ge=1, le=1000, alias="TRANSCRIBE_MAX_JOBS_STORED"
    )
    proxy_cookie_token_max: int = Field(
        default=2048, ge=16, le=100_000, alias="PROXY_COOKIE_TOKEN_MAX"
    )

    # ----- Auto-generated subtitles (Groq Whisper speech-to-text) ---------
    # Transcription only -- speech becomes text in whatever language it was
    # spoken, no translation direction involved. Free at console.groq.com,
    # no card required. Empty disables /transcribe (503 instead of failing
    # mid-pipeline). SEVERAL keys may be given, comma-separated -- requests
    # spread across them and a rate-limited key rotates out instead of
    # stalling the job, so extra keys directly raise throughput.
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    transcribe_enabled: bool = Field(default=True)
    # Concurrent transcription jobs across all clients — each one pins a
    # Groq-rate-limited pipeline plus local ffmpeg CPU work.
    transcribe_max_concurrent_jobs: int = Field(default=2, ge=1, le=10)
    # Hard cap on the one audio/video stream a job downloads to disk (the
    # only place in the app that writes media bytes to disk).
    transcribe_max_download_bytes: int = Field(default=300_000_000, ge=1_000_000)
    # How long a finished/errored job's result stays available for polling
    # and subtitle-file downloads before it's swept from memory.
    transcribe_job_ttl: int = Field(default=1800, ge=60)
    # Whole-job wall-clock cap; a stuck/very slow job is killed and reported
    # as an error rather than running forever.
    transcribe_job_timeout: int = Field(default=900, ge=60, le=3600, alias="TRANSCRIBE_JOB_TIMEOUT")
    # Bounds concurrent CPU-heavy pipeline steps (audio transcode + dialogue map
    # extraction) separately from transcribe_max_concurrent_jobs, which only
    # gates overall job admission -- without this a small VPS could end up
    # running several ffmpeg transcodes at once even though it's fine to have
    # more jobs than that merely waiting on a Groq network round-trip.
    transcribe_workers: int = Field(default=2, ge=1, le=8)
    groq_whisper_model: str = Field(default="whisper-large-v3-turbo")

    # ----- Extraction speed (transcription pipeline) ----------------------
    # The source is pulled as several cap-sized time windows extracted in
    # parallel (each its own ffmpeg -ss/-t Range read) instead of one
    # sequential pass, and each finished window uploads to Groq while later
    # ones are still downloading. On a network-bound extract (idle CPU, slow
    # "Extracting audio…") this is the big win: it uses the spare cores AND
    # sidesteps the per-connection throttling many CDNs (googlevideo) apply.
    #
    # How many windows extract at once. More = faster on throttled/large
    # sources, but more simultaneous connections to the origin -- drop it to
    # 1-2 if a site starts answering 429/"used too much".
    transcribe_extract_parallelism: int = Field(
        default=4, ge=1, le=16, alias="TRANSCRIBE_EXTRACT_PARALLELISM"
    )
    # The hard per-file upload cap Groq enforces (MB). Free tier is 25 today;
    # bump this if your plan allows more. Window sizing targets ~80% of it so
    # a chunk never trips the API's 413. Also gates the engine's own guard.
    transcribe_max_upload_mb: int = Field(
        default=25, ge=1, le=200, alias="TRANSCRIBE_MAX_UPLOAD_MB"
    )
    # Intermediate audio codec fed to Whisper: "opus" | "wav" | "flac".
    # opus (default) is tiny (~1.2MB/5min) with ample headroom; wav is
    # zero-encode-CPU but ~8x larger (fewer, longer windows under the cap);
    # flac sits between. All are mono/16kHz -- Whisper's native rate.
    # In "auto" mode (below) this is only the floor the picker falls back to;
    # in "custom" mode it's ignored in favour of TRANSCRIBE_CUSTOM_FFMPEG_ARGS.
    transcribe_audio_codec: str = Field(default="opus", alias="TRANSCRIBE_AUDIO_CODEC")

    # How the audio fed to Whisper is encoded:
    #   "auto"   -- pick the FASTEST encode whose whole track still fits one
    #               upload window (wav=zero-CPU/biggest -> flac -> opus=smallest);
    #               only reach for heavy compression (and chunking) when the
    #               track is too long to fit the cap otherwise. Best default:
    #               short clips skip the encode CPU, long ones stay under the cap.
    #   "custom" -- use TRANSCRIBE_CUSTOM_FFMPEG_ARGS verbatim (operator knows best).
    transcribe_mode: str = Field(default="auto", alias="TRANSCRIBE_MODE")
    # Custom-mode ffmpeg output args (shlex-split), applied after "-i <src>" and
    # before the output path. MUST drop video (-vn) and produce a Whisper-friendly
    # mono track, e.g. "-vn -ac 1 -ar 16000 -c:a libopus -b:a 24k". Empty falls
    # back to the opus preset. Server-side only (never user-supplied) -- these are
    # raw ffmpeg args, so they stay operator-controlled.
    transcribe_custom_ffmpeg_args: str = Field(
        default="", alias="TRANSCRIBE_CUSTOM_FFMPEG_ARGS"
    )
    # Custom-mode encoded-bytes-per-second estimate, used only to size upload
    # windows so a chunk stays under the cap. Match it to your custom bitrate
    # (e.g. 24kbps opus ~= 3000). Default mirrors the opus preset.
    transcribe_custom_bytes_per_second: float = Field(
        default=4_000.0, gt=0, alias="TRANSCRIBE_CUSTOM_BYTES_PER_SECOND"
    )
    # Custom-mode output file extension (container ffmpeg writes). Match your
    # codec (opus->"opus", pcm->"wav", flac->"flac", aac->"m4a").
    transcribe_custom_ext: str = Field(default="opus", alias="TRANSCRIBE_CUSTOM_EXT")

    # ----- Image/gallery extraction (gallery-dl) ---------------------------
    gallery_dl_timeout: int = Field(default=45, ge=5)
    gallery_dl_workers: int = Field(default=3, ge=1, le=20)
    gallery_dl_binary: str = Field(default="gallery-dl")
    # Hard cap on images returned per gallery extract (large albums).
    gallery_max_images: int = Field(default=200, ge=1, le=5000, alias="GALLERY_MAX_IMAGES")

    # ----- ffmpeg/ffprobe (transcription pipeline only) --------------------
    # Bare names rely on the running process's PATH, which is NOT always the
    # same PATH an interactive shell sees (systemd services, some containers,
    # or a dev machine where ffmpeg was only added to a shell profile). Point
    # these at an absolute path if `/health` reports either as unavailable.
    ffmpeg_binary: str = Field(default="ffmpeg", alias="FFMPEG_BINARY")
    ffprobe_binary: str = Field(default="ffprobe", alias="FFPROBE_BINARY")

    # ----- Proxy security ---------------------------------------------------
    # The media proxy (GET /proxy-video) fetches arbitrary user-supplied URLs.
    # Without a host allow-list this is open to SSRF abuse on a public deploy.
    # Set PROXY_ALLOWED_HOSTS to a comma-separated list of allowed destination
    # hostnames (e.g. "googlevideo.com,cdninstagram.com,fbcdn.net") to restrict
    # proxying to known media CDNs. PROXY_ENABLED=false disables the proxy
    # entirely — the client falls back to direct (non-proxied) playback, which
    # works for most sites except those that gate on Referer/Cookie headers.
    proxy_enabled: bool = Field(default=True, alias="PROXY_ENABLED")
    proxy_allowed_hosts_raw: str = Field(default="", alias="PROXY_ALLOWED_HOSTS")

    user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()] or ["*"]

    @property
    def transcribe_max_upload_bytes(self) -> int:
        """Groq's per-file cap in bytes (from ``transcribe_max_upload_mb``)."""
        return self.transcribe_max_upload_mb * 1024 * 1024

    @property
    def transcribe_custom_ffmpeg_arg_list(self) -> list[str]:
        """Custom-mode ffmpeg output args, shlex-split. Empty when unset."""
        import shlex

        return shlex.split(self.transcribe_custom_ffmpeg_args.strip())

    @property
    def groq_api_keys(self) -> list[str]:
        return [k.strip() for k in self.groq_api_key.split(",") if k.strip()]

    @property
    def cookie_files(self) -> list[str]:
        return [p.strip() for p in self.cookie_file.split(",") if p.strip()]

    @property
    def youtube_player_client_list(self) -> list[str]:
        return [c.strip() for c in self.youtube_player_clients.split(",") if c.strip()]

    @property
    def youtube_po_token_list(self) -> list[str]:
        return [t.strip() for t in self.youtube_po_token.split(",") if t.strip()]

    @property
    def proxy_allowed_hosts(self) -> list[str]:
        """Proxy destination hostnames from PROXY_ALLOWED_HOSTS; empty = allow all."""
        return [h.strip().lower() for h in self.proxy_allowed_hosts_raw.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
