# MediaPull server

FastAPI backend for **MediaPull**: extract video formats (yt-dlp), image
galleries (gallery-dl), and optional speech-to-text subtitles (Groq Whisper).

## Setup

```bash
# Python 3.10+
pip install -r requirements.txt
cp .env.example .env
# edit .env — at minimum set CORS_ORIGINS; set GROQ_API_KEY for subtitles
python -m app
# → http://localhost:8000
```

yt-dlp and gallery-dl must be installed and on PATH (or available as Python
packages — they're in `requirements.txt`). ffmpeg is required for subtitles.

## Configuration

All config via `server/.env` (see `.env.example`).

### Essential

| Variable | Default | Purpose |
|----------|---------|---------|
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `8000` | Listen port |
| `CORS_ORIGINS` | `*` | Comma-separated allowed client origins. **Pin an explicit origin in prod** — with the `*` default, credentialed CORS is disabled automatically (browsers reject `Access-Control-Allow-Origin: *` with credentials), so cross-origin auth fails silently. |

### Optional features

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROQ_API_KEY` | — | Groq Whisper for subtitles. Empty = disabled. |
| `TRANSCRIBE_ENABLED` | `true` | Master toggle for subtitle feature |
| `COOKIE_FILE` | — | Shared cookies file (Netscape format). Enables age-gated/login content. |
| `PROXY_URL` | — | Outbound proxy for extraction and streaming |
| `ENABLE_IMPERSONATION` | `true` | Browser impersonation to bypass anti-bot blocks |

### Tuning

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_FORMATS` | `40` | Cap on returned formats per video |
| `REQUEST_TIMEOUT` | `90` | Extraction timeout (seconds) |
| `EXTRACT_WORKERS` | `4` | Concurrent extraction subprocesses |
| `CACHE_TTL` | `300` | Response cache TTL (seconds) |
| `TRANSCRIBE_MAX_CONCURRENT_JOBS` | `2` | Parallel subtitle jobs |
| `TRANSCRIBE_MAX_DOWNLOAD_BYTES` | `300000000` | Audio download cap (300 MB) |
| `TRANSCRIBE_JOB_TIMEOUT` | `900` | Whole-job wall-clock cap (s). A stuck job is killed and reported as an error rather than holding a slot forever. |

### Proxy security

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROXY_ENABLED` | `true` | Master switch for `GET /proxy-video`. `false` = client plays sources directly (no header injection). |
| `PROXY_ALLOWED_HOSTS` | — | Comma-separated destination host allow-list (e.g. `googlevideo.com,cdninstagram.com,fbcdn.net`). Empty = allow any public host. **Set this on a public deploy.** |

## Proxying & security

`GET /proxy-video` streams media from the source host so the frontend stays
behind one origin, injecting the Referer/Cookie/User-Agent a `<video>` element
can't set.

- **SSRF guard**: rejects internal targets (loopback, RFC-1918, link-local,
  IPv4-mapped IPv6) and re-checks the host on every redirect hop and against
  resolved DNS. Add `PROXY_ALLOWED_HOSTS` (or `PROXY_ENABLED=false`) on a
  public box.
- **Cookie tokens**: clients never put auth cookies in a proxy URL. They call
  `POST /proxy-token` to swap cookies for a short-lived opaque token, which the
  proxy resolves server-side — so copied/QR/shared links can't leak a session.

## Architecture notes

- **No database.** All state per-request or in-memory.
- **Single worker.** In-memory job tracking means one process. Don't set
  `WORKERS` > 1 unless you add external shared state (Redis, db).
- **Subprocess extraction.** yt-dlp/gallery-dl run as subprocesses, not
  libraries. Keeps them independently updatable (`pip install -U …`).

## Testing

```bash
pip install -r requirements.txt   # includes pytest + pytest-asyncio
python -m pytest -q               # unit + characterization tests
ruff check app/                   # lint
```

## Full docs

- [Deployment (VPS)](../deploy/README.md)
- [Project overview](../README.md)
