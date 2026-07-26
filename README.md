# MediaPull


MediaPull turns a page URL into downloadable video formats and/or image
galleries. Paste a link, extract, then preview, download, or copy. Optional
speech-to-text subtitles (Groq Whisper), cookie support for signed-in sites,
and a media proxy when the browser can’t play a source directly.

Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for video and
[gallery-dl](https://github.com/mikf/gallery-dl) for images.

## Features

- **Extract video formats** — qualities and container types, ready to preview,
  download, or copy
- **Image galleries** — pull albums/galleries with per-image and bulk download
- **Built-in player** — preview in the page; switch quality without leaving
- **Auto / Video / Gallery** — Auto detects type; force Video or Gallery from
  the extract bar when you already know
- **Subtitles, two ways** — use caption tracks the source already provides, or
  auto-generate them with speech-to-text (Groq Whisper) when `GROQ_API_KEY` is
  set; browse the transcript in a side panel and download as SRT
- **Proxy mode** — stream through the backend when direct play fails (hotlink
  protection, missing Referer/Cookie headers)
- **Sign-in cookies** — Settings → Sign-in for sites that need a login
- **Bilingual** — English and Persian (RTL-aware)

## Quick start

### One-click start (Windows)

No terminal needed:

1. Download the repo (**Code → Download ZIP** on GitHub, or clone it) and
   unzip it anywhere.
2. Double-click **`start-windows.bat`** in the repo root.

On the first run it checks for Python 3.11+ and Node.js 18+ (and points you
at [python.org](https://www.python.org/downloads/) /
[nodejs.org](https://nodejs.org/) if they're missing), installs everything
into `server/.venv` and `client/node_modules`, and creates `server/.env` +
`client/.env` from the examples — existing `.env` files are never touched.
Every run after that skips straight to launching the server and client in two
console windows and opening http://localhost:5173 in your browser. To stop
MediaPull, just close those two windows — there's no separate stop script.

Subtitle generation additionally needs [ffmpeg](https://ffmpeg.org/) on PATH
and a `GROQ_API_KEY` in `server/.env`.

Prefer typing the commands yourself, or on macOS/Linux? Read on.

### 1. Install

```bash
git clone https://github.com/meowbey/MediaPull.git
cd mediapull
```

**Server** (Python 3.10+):

```bash
cd server
pip install -r requirements.txt
cp .env.example .env        # optional: CORS_ORIGINS, GROQ_API_KEY, COOKIE_FILE_PATHS, …
```

**Client** (Node.js 18+):

```bash
cd client
npm install
cp .env.example .env        # leave VITE_API_BASE_URL empty in dev (Vite proxies)
```

### 2. Run

```bash
# Terminal 1 — backend
cd server
uvicorn app.main:app --reload      # or: python run.py

# Terminal 2 — frontend
cd client
npm run dev
```

Open **http://localhost:5173** — the Vite dev server proxies API routes to
http://localhost:8000 (including `/proxy-token`).

### 3. Use it

1. Paste a URL into the input field.
2. Leave mode on **Auto** (or pick **Video** / **Gallery**), then **Extract**.
3. Preview, then **Download** or **Copy** the link you want.
4. For login-only sites, add cookies in **Settings → Sign-in** and try again.

Want subtitles? Set `GROQ_API_KEY` in `server/.env`, then use **Subtitles** on
a video card.

## How it works

The browser never talks to the source site — only to the MediaPull backend.
That's the whole trick: the backend can send the `Referer` / `Cookie` /
`User-Agent` headers a plain `<video>` tag cannot, so extraction and playback
work on sites that block hotlinking or require a login.

```mermaid
flowchart LR
    browser([Browser<br/>SvelteKit client]) --> api[FastAPI backend]
    api -- "/extract-videos" --> ytdlp[yt-dlp<br/>video format links]
    api -- "/extract-gallery" --> gdl[gallery-dl<br/>image lists]
    api -- "/proxy-video" --> proxy[media proxy<br/>real browser headers]
    api -- "/transcribe" --> whisper[Groq Whisper<br/>optional subtitles]
```

**Worth knowing:**

- **Cookies stay off proxy URLs.** Before a proxy URL is built, auth cookies
  are swapped for a short-lived opaque token (`ctok` via `/proxy-token`), so
  copied, QR'd, or shared links never expose a session.
- **Single-worker by design.** Result cache, transcription jobs, and proxy
  tokens are in-memory per process — scale with more instances behind a load
  balancer, not more workers in one process.
- **Keep scrapers current.** When extraction breaks after site changes, upgrade
  yt-dlp/gallery-dl (`pip install -U yt-dlp gallery-dl`). There is no built-in
  auto-update of those tools.

## Configuration

All server config comes from environment variables, loaded from `server/.env`
(copy `server/.env.example`; `server/.env.production.example` is a
production-leaning starting point). Every variable has a working default —
an empty `.env` runs fine in dev. The client has exactly one variable, in
`client/.env`.

### Client

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | *(empty)* | Backend origin. Leave empty in dev (Vite proxies API routes to `http://localhost:8000`); set to the API origin (e.g. `https://api.example.com`) for split/static deploys. Build-time, not runtime. |

### Server — core

| Variable | Default | Purpose |
|---|---|---|
| `DEBUG` | `false` | Uvicorn reload + access logs (via `run.py`) |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `HOST` | `0.0.0.0` | Bind address (`run.py`) |
| `PORT` | `8000` | Listen port (`run.py`; under systemd the unit's `--bind` wins) |
| `WORKERS` | `1` | **Must stay 1** — jobs, caches, and proxy tokens are in-process; scale with more instances, not workers |
| `CORS_ORIGINS` | `*` | Comma-separated allowed browser origins. Pin explicitly in production — `*` disables credentialed CORS |
| `CLIENT_DIR` | *(auto)* | Directory of the built client to serve same-origin; empty auto-detects `client/build`. Leave empty in dev |

### Server — extraction (video)

| Variable | Default | Purpose |
|---|---|---|
| `MAX_FORMATS` | `40` | Formats kept per video after ranking |
| `REQUEST_TIMEOUT` | `90` | yt-dlp / scrape overall seconds |
| `MAX_RETRIES` | `2` | Retries on transient extract failures |
| `SCRAPE_MAX_BYTES` | `200000` | HTML scrape body cap |
| `EXTRACT_WORKERS` | `4` | Thread pool for blocking yt-dlp work |
| `EXTRACT_MAX_IN_FLIGHT` | `8` | Concurrent non-cached extracts before 503 "Server busy" |
| `CACHE_TTL` | `300` | Extraction result cache TTL, seconds (`0` disables) |
| `CACHE_MAX_ENTRIES` | `512` | Cache size cap (`0` disables) |
| `VALIDATE_FORMATS` | `true` | Probe extracted URLs; drop only confirmed-dead ones |
| `VALIDATE_TIMEOUT` | `6` | Per-probe seconds |
| `VALIDATE_CONCURRENCY` | `10` | Parallel probes |
| `VALIDATE_MAX_FORMATS` | `8` | Max unique URLs probed per extract |

### Server — auth / anti-block

| Variable | Default | Purpose |
|---|---|---|
| `COOKIE_FILE_PATHS` | *(empty)* | Server-side default cookies (Netscape `cookies.txt`), comma-separated for rotation. Unlocks login-gated/age-restricted content |
| `MAX_COOKIE_BYTES` | `262144` | Cap on per-request cookie blobs from the client |
| `ADMIN_TOKEN` | *(empty)* | Enables `POST /admin/cookies` (push fresh cookies without redeploy). Empty = endpoint returns 404 |
| `PROXY_URL` | *(empty)* | Outbound http/https/socks5 proxy for extraction and the media proxy |
| `YOUTUBE_PLAYER_CLIENTS` | *(empty)* | yt-dlp `player_client` list, e.g. `default,tv,web_safari` |
| `YOUTUBE_POT_BASE_URL` | *(empty)* | bgutil PO-token sidecar URL; only needed off the default `127.0.0.1:4416` |
| `SLEEP_REQUESTS` | `0` | Random sleep between extractor HTTP requests (1–3 cuts 429s) |
| `ENABLE_IMPERSONATION` | `true` | Browser TLS fingerprint impersonation (curl_cffi) |
| `IMPERSONATE_CLIENT` | `chrome` | curl_cffi impersonation target |
| `USER_AGENT` | Chrome UA | User-Agent for extraction/proxy requests |

### Server — media proxy

| Variable | Default | Purpose |
|---|---|---|
| `PROXY_ENABLED` | `true` | Master switch for `GET /proxy-video`; `false` = direct playback only |
| `PROXY_ALLOWED_HOSTS` | *(empty)* | Comma-separated destination allow-list (e.g. `googlevideo.com,cdninstagram.com`). **Set on public deploys** — empty allows any public host |
| `PROXY_COOKIE_TOKEN_MAX` | `2048` | Cap on live `/proxy-token` entries |

### Server — subtitles (Groq Whisper)

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Enables `/transcribe`. Comma-separate several keys to rotate around rate limits. Free at console.groq.com |
| `TRANSCRIBE_ENABLED` | `true` | Master toggle for the feature |
| `TRANSCRIBE_MAX_CONCURRENT_JOBS` | `2` | Parallel transcription jobs |
| `TRANSCRIBE_WORKERS` | `2` | Parallel CPU-heavy ffmpeg steps |
| `TRANSCRIBE_MAX_DOWNLOAD_BYTES` | `300000000` | Cap on the audio/video a job downloads |
| `TRANSCRIBE_MAX_JOBS_STORED` | `64` | Finished+running jobs kept in RAM |
| `TRANSCRIBE_JOB_TTL` | `1800` | Seconds a finished job stays pollable |
| `TRANSCRIBE_JOB_TIMEOUT` | `900` | Whole-job wall-clock kill switch |
| `TRANSCRIBE_EXTRACT_PARALLELISM` | `4` | Parallel audio extraction windows |
| `TRANSCRIBE_MAX_UPLOAD_MB` | `25` | Groq per-file upload cap (free tier: 25) |
| `TRANSCRIBE_AUDIO_CODEC` | `opus` | Intermediate codec: `opus` / `wav` / `flac` |
| `TRANSCRIBE_MODE` | `auto` | `auto` picks the fastest encode that fits the cap; `custom` uses the args below |
| `TRANSCRIBE_CUSTOM_FFMPEG_ARGS` | *(empty)* | Custom-mode ffmpeg output args |
| `TRANSCRIBE_CUSTOM_BYTES_PER_SECOND` | `4000` | Custom-mode size estimate for window sizing |
| `TRANSCRIBE_CUSTOM_EXT` | `opus` | Custom-mode output extension |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | Whisper model name |
| `FFMPEG_PATH` / `FFPROBE_PATH` | `ffmpeg` / `ffprobe` | Absolute paths if not on the service's PATH |

### Server — galleries (gallery-dl)

| Variable | Default | Purpose |
|---|---|---|
| `GALLERY_DL_TIMEOUT` | `45` | Wall-clock cap per gallery-dl run |
| `GALLERY_DL_WORKERS` | `3` | Concurrent gallery-dl processes |
| `GALLERY_DL_PATH` | `gallery-dl` | Binary path override |
| `GALLERY_MAX_IMAGES` | `200` | Images returned per extract (larger albums are truncated with a warning) |

The same tables with more operational context live in
[server/README.md](server/README.md); the authoritative list is
[`server/app/config.py`](server/app/config.py).

## Deployment

[`deploy/`](deploy/README.md) holds a native (no Docker) VPS install:

- `install.sh` — interactive one-shot provisioner: system packages, service
  user, clone into `/opt/mediapull`, Python venv, **systemd** unit
  (`mediapull.service`, single-worker gunicorn/uvicorn behind `127.0.0.1`),
  **nginx** reverse proxy + Let's Encrypt TLS (Caddyfile example included),
  firewall, optional client build, and the optional YouTube PO-token sidecar
  (`mediapull-pot.service`)
- `update.sh` — pull, reinstall deps, upgrade yt-dlp/gallery-dl, rebuild
  client, restart, health-check
- `uninstall.sh` — remove the service/nginx sites; `--purge` wipes everything

See [deploy/README.md](deploy/README.md) for the full walkthrough, including
a manual step-by-step equivalent, YouTube PO tokens, server-wide cookies, and
security notes.

## Testing

```bash
# Server (from server/)
ruff check app/
pytest -q

# Client (from client/)
npm run check
npm run lint
npm test
```

## Documentation

- **[Server setup](server/README.md)** — backend config, env vars, security
- **[Client setup](client/README.md)** — frontend build, routing, dev mode
- **[Deployment](deploy/README.md)** — VPS install (systemd + nginx/Caddy)

## Production notes

- Pin `CORS_ORIGINS` to your real frontend origin(s) (not `*`) if you need
  credentialed cross-origin requests.
- On a public VPS, set `PROXY_ALLOWED_HOSTS` to known media CDNs so the media
  proxy isn’t an open relay.
- Upgrade `yt-dlp` when extraction fails against sites that change often.

## Responsible use

MediaPull is a tool for pulling media you are **authorized to download** — your
own uploads, content you have rights to, or material whose license permits it.
You are responsible for complying with the terms of service of the sites you
point it at and with the copyright law of your jurisdiction. Don't use it to
infringe copyright or bypass access controls you aren't entitled to.

## License

[MIT](LICENSE)
