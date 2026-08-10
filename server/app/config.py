"""Runtime configuration, loaded once from the environment."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    # Must stay 1 for public deploys: JobStore, extract caches, and proxy ctok
    # maps are in-process only. Scale out with multiple instances + a load
    # balancer, not multi-worker uvicorn on one box.
    workers: int = Field(default=1)

    # Comma-separated browser origins allowed to call the API. Default "*"
    # disables credentialed CORS (browsers reject `*` + credentials together).
    # Pin explicit origins in production (see .env.production.example).
    cors_origins_raw: str = Field(default="*", alias="CORS_ORIGINS")

    # Single-process deploy: directory of the built static client to serve from
    # the same origin as the API. Empty -> auto-detect repo-root/client/build.
    # Leave empty in dev (Vite serves the SPA on :5173).
    client_dir: str = Field(default="", alias="CLIENT_DIR")

    # Extraction tuning (video). Gallery has its own GALLERY_* knobs below.
    max_formats: int = Field(default=40, ge=1, le=200)  # formats kept per video after ranking
    request_timeout: int = Field(default=90, ge=5)  # yt-dlp / scrape overall seconds
    max_retries: int = Field(default=2, ge=0)  # transient extract failures
    scrape_max_bytes: int = Field(default=200_000, ge=1_000)  # HTML scrape body cap

    # ----- Authentication / anti-block -----------------------------------
    # Server-side default cookies (Netscape cookies.txt path). Unlocks
    # age-restricted / private / login-gated content (YouTube, Instagram, …)
    # and tames "sign in to confirm you're not a bot" on datacenter IPs. Used
    # only when the request carries no per-user cookies of its own. Empty = off.
    # May hold SEVERAL comma-separated paths (e.g. two Instagram accounts) --
    # extraction rotates round-robin across them, and a file whose account is
    # rate-limited / bot-flagged goes on cooldown while the others keep serving.
    cookie_file_paths_raw: str = Field(default="", alias="COOKIE_FILE_PATHS")
    # The per-request cookie blob size cap is a fixed schema constraint --
    # see models.MAX_COOKIE_BYTES (Pydantic field limits can't read settings).
    # Shared secret gating the admin cookie-refresh endpoint (POST /admin/cookies).
    # Empty = endpoint disabled (returns 404), so the feature is opt-in and a
    # default deploy exposes no new surface. Set a long random value to enable
    # pushing freshly-exported cookies to the server without a redeploy.
    admin_token: str = Field(default="", alias="ADMIN_TOKEN")

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
    # Base URL of the bgutil PO-token provider sidecar (see the VPS installer).
    # yt-dlp's bgutil HTTP plugin auto-detects http://127.0.0.1:4416, so this
    # only needs setting when the provider runs on a NON-default port (e.g. 4416
    # was already taken). Maps to extractor_args youtubepot-bgutilhttp:base_url.
    youtube_pot_base_url: str = Field(default="", alias="YOUTUBE_POT_BASE_URL")

    # Politeness: random sleep (seconds) between extractor HTTP requests. A
    # small value (1–3) markedly cuts 429/"used too much" blocks under load.
    sleep_requests: float = Field(default=0.0, ge=0, alias="SLEEP_REQUESTS")

    # Browser impersonation (curl_cffi): mimics a real browser's TLS/HTTP
    # fingerprint so anti-bot sites (TikTok, …) stop answering with 403/410.
    # Used by extraction probes and the media proxy. No-op if curl_cffi isn't
    # installed. impersonate_client is the curl_cffi target name (e.g. "chrome").
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
    # Unprobed formats stay in the list — same as an "uncertain" probe. Raise
    # only if you routinely need more live checks; each probe is an extra
    # outbound request under VALIDATE_TIMEOUT / VALIDATE_CONCURRENCY.
    validate_max_formats: int = Field(default=8, ge=1, le=200, alias="VALIDATE_MAX_FORMATS")

    # Thread-pool size for blocking yt-dlp work only (gallery-dl has its own
    # GALLERY_DL_WORKERS pool). Raise on a multi-core box if video extracts
    # queue under concurrent users; each worker holds a full run (network + CPU).
    extract_workers: int = Field(default=4, ge=1, le=32)

    # In-memory extraction result cache (separate video + gallery stores in main).
    # cache_ttl=0 or cache_max_entries=0 disables caching entirely.
    cache_ttl: int = Field(default=300, ge=0)
    cache_max_entries: int = Field(default=512, ge=0)

    # ----- Admission control (single-worker public deploys) ----------------
    # These are hard caps so a burst of users cannot OOM / thrash one process.
    # WORKERS must stay 1: JobStore, TTLCache, and cookie tokens are in-process
    # only (not shared across multi-worker uvicorn).
    #
    # Concurrent /extract-videos + /extract-gallery requests that actually run
    # (not cache hits). Overflow gets 503 "Server busy" after a tiny wait —
    # shared admission gate so both engines cannot pile up unbounded work.
    extract_max_in_flight: int = Field(default=8, ge=1, le=64, alias="EXTRACT_MAX_IN_FLIGHT")
    # Max finished+running transcription jobs kept in RAM at once (each holds
    # VTT/SRT text + dialogue peaks). Create returns 503 when full until TTL
    # sweep frees slots (see TRANSCRIBE_JOB_TTL).
    transcribe_max_jobs_stored: int = Field(
        default=64, ge=1, le=1000, alias="TRANSCRIBE_MAX_JOBS_STORED"
    )
    # Cap on live POST /proxy-token entries (cookie blob → opaque ctok). When
    # full, oldest-expiring tokens are evicted so minting never fails hard.
    # Raise if many users share one server with heavy cookie-gated media.
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
    # Hard cap on any client-supplied source: the one audio/video stream a job
    # downloads to disk, a local file uploaded for transcription, or the source
    # fed to the splitter. One knob for all three so the client's single size
    # check (health.mediaMaxBytes) can never disagree with the server.
    # Legacy names TRANSCRIBE_MAX_DOWNLOAD_BYTES and SPLIT_AUDIO_MAX_BYTES
    # still work; MEDIA_MAX_SOURCE_BYTES wins when both are set.
    media_max_source_bytes: int = Field(
        default=300_000_000,
        ge=1_000_000,
        validation_alias=AliasChoices(
            "MEDIA_MAX_SOURCE_BYTES",
            "TRANSCRIBE_MAX_DOWNLOAD_BYTES",
            "SPLIT_AUDIO_MAX_BYTES",
        ),
    )
    # How long a finished/errored job's result stays available for polling
    # and subtitle-file downloads before it's swept from memory.
    transcribe_job_ttl: int = Field(default=1800, ge=60)
    # Whole-job wall-clock cap; a stuck/very slow job is killed and reported
    # as an error rather than running forever.
    transcribe_job_timeout: int = Field(default=3600, ge=60, le=21600, alias="TRANSCRIBE_JOB_TIMEOUT")
    # Bounds concurrent CPU-heavy pipeline steps (audio transcode + dialogue map
    # extraction) separately from transcribe_max_concurrent_jobs, which only
    # gates overall job admission -- without this a small VPS could end up
    # running several ffmpeg transcodes at once even though it's fine to have
    # more jobs than that merely waiting on a Groq network round-trip.
    transcribe_workers: int = Field(default=2, ge=1, le=8)
    groq_whisper_model: str = Field(default="whisper-large-v3-turbo")
    # Seeded into each Whisper request as prior context — nudges the model to
    # transcribe spoken words only and skip noise/music hallucinations and
    # boundary repetitions. Set to an empty string to send no prompt (raw
    # Whisper output).
    transcribe_whisper_prompt: str = Field(
        default=(
            "Transcribe only the words that are actually spoken, exactly as said. "
            "Ignore music, singing, sound effects, and background noise: never "
            "describe them and never add symbols like ♪ or tags like [Music], "
            "[Applause], or [Laughter]. Do not repeat or duplicate any phrase, "
            "and do not invent words that were not spoken — if the same line is "
            "truly said twice, transcribe it twice. Always add punctuation: a "
            "period or question mark when a sentence ends, a comma for a pause."
        ),
        alias="TRANSCRIBE_WHISPER_PROMPT",
    )
    # Run a post-processing pass on Whisper output to strip remaining noise
    # placeholders, consecutive duplicates, and sub-0.5s isolated single-word
    # cues. Applied to every job (online and local). Set false for raw output.
    transcribe_postprocess: bool = Field(default=True, alias="TRANSCRIBE_POSTPROCESS")
    # Split long cues (fast dialogue / several speakers often arrives as one
    # long Whisper segment) into shorter readable ones. With word timestamps
    # (always returned by whisper-large-v3-turbo) the split is exact — each
    # new cue starts at its first word and ends at its last, so no timing
    # shifts. Without them, postprocess falls back to an approximate
    # proportional split. Set false to keep Whisper's cue boundaries as-is.
    transcribe_split_long_cues: bool = Field(
        default=True, alias="TRANSCRIBE_SPLIT_LONG_CUES"
    )

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
    # windows so a chunk stays under the cap. Match it to your custom bitrate:
    # bytes/s ≈ bitrate_kbps * 125 (e.g. 32kbps opus ≈ 4000 — the built-in
    # preset; 24kbps ≈ 3000). Default mirrors the opus preset's 32kbps.
    transcribe_custom_bytes_per_second: float = Field(
        default=4_000.0, gt=0, alias="TRANSCRIBE_CUSTOM_BYTES_PER_SECOND"
    )
    # Custom-mode output file extension (container ffmpeg writes). Match your
    # codec (opus->"opus", pcm->"wav", flac->"flac", aac->"m4a").
    transcribe_custom_ext: str = Field(default="opus", alias="TRANSCRIBE_CUSTOM_EXT")

    # ----- Image/gallery extraction (gallery-dl) ---------------------------
    # Wall-clock cap (seconds) for one gallery-dl subprocess run.
    gallery_dl_timeout: int = Field(default=45, ge=5)
    # Concurrent gallery-dl processes (separate from EXTRACT_WORKERS).
    gallery_dl_workers: int = Field(default=3, ge=1, le=20)
    # Default "gallery-dl" uses `python -m gallery_dl` when the package is
    # installed; set an absolute path to force a specific binary instead.
    gallery_dl_path: str = Field(default="gallery-dl", alias="GALLERY_DL_PATH")
    # Hard cap on images returned per gallery extract. Large albums are
    # truncated (client gets a soft "truncated" warning); raise for bulk dumps.
    gallery_max_images: int = Field(default=200, ge=1, le=5000, alias="GALLERY_MAX_IMAGES")

    # ----- Local file + split-audio features ------------------------------
    # Allow users to open local files (video/audio) directly in the player.
    # Client-side only (blob URL, no upload). Gated separately so a public
    # server operator can disable it without touching transcription.
    local_files_enabled: bool = Field(default=True, alias="LOCAL_FILES_ENABLED")

    # Enable the split-audio endpoints (POST /split-audio/*). ffmpeg strips
    # the video track, writes the audio to a temp file, and holds it for
    # SPLIT_AUDIO_TTL seconds so the user can download it. Set false to
    # disable without affecting transcription.
    split_audio_enabled: bool = Field(default=True, alias="SPLIT_AUDIO_ENABLED")
    # Seconds to keep a split audio file before it is deleted. Short enough to
    # not accumulate disk use; long enough for a slow download.
    split_audio_ttl: int = Field(default=300, ge=30, le=3600, alias="SPLIT_AUDIO_TTL")

    # ----- ffmpeg/ffprobe (transcription pipeline only) --------------------
    # Bare names rely on the running process's PATH, which is NOT always the
    # same PATH an interactive shell sees (systemd services, some containers,
    # or a dev machine where ffmpeg was only added to a shell profile). Point
    # these at an absolute path if `/health` reports either as unavailable.
    ffmpeg_path: str = Field(default="ffmpeg", alias="FFMPEG_PATH")
    ffprobe_path: str = Field(default="ffprobe", alias="FFPROBE_PATH")

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
    def cookie_file_paths(self) -> list[str]:
        return [p.strip() for p in self.cookie_file_paths_raw.split(",") if p.strip()]

    @property
    def youtube_player_client_list(self) -> list[str]:
        return [c.strip() for c in self.youtube_player_clients.split(",") if c.strip()]

    @property
    def pot_probe_url(self) -> str:
        """Base URL to health-check the bgutil PO-token sidecar at boot. Uses
        YOUTUBE_POT_BASE_URL when set, else the plugin's auto-detect default
        (127.0.0.1:4416) -- so /health reflects the same provider yt-dlp will
        actually reach."""
        return self.youtube_pot_base_url.strip() or "http://127.0.0.1:4416"

    @property
    def proxy_allowed_hosts(self) -> list[str]:
        """Proxy destination hostnames from PROXY_ALLOWED_HOSTS; empty = allow all."""
        return [h.strip().lower() for h in self.proxy_allowed_hosts_raw.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
