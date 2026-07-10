# DirectStream

Extract direct video/image links from any webpage, then preview them in a
built-in player, download them, or stream them through an optional proxy.
Also generates auto-subtitles for videos that don't already have captions.

DirectStream is a static web client backed by a single Python service:

- **Client** — a SvelteKit **static SPA** (UI, in-browser HLS player, result
  management). No server runtime: it builds to plain static files.
- **Server** — a Python FastAPI service that does everything backend: video
  link extraction with [yt-dlp](https://github.com/yt-dlp/yt-dlp) (+ generic
  and HTML-scrape fallbacks), image/gallery extraction with
  [gallery-dl](https://github.com/mikf/gallery-dl) (Instagram, X/Twitter,
  etc.), a streaming media **proxy** (with HLS rewriting and Range support)
  that impersonates a browser so blocked CDNs still play, and an optional
  **auto-subtitles** pipeline (speech-to-text via Groq's Whisper API).

> For educational use. You are responsible for complying with the terms of
> service of any site you point it at and with applicable copyright law.

## How it works

1. You paste a webpage URL in the client.
2. **Auto mode (the default)**: the client tries video extraction
   (`POST /extract-videos`) first; if that comes back empty, it silently
   retries as a gallery/image extraction (`POST /extract-gallery`) — no need
   to tell it which kind of page you're pasting. You can force one or the
   other from **Settings → Content type** if you'd rather pick manually every
   time (e.g. you know a page is an Instagram photo carousel).
3. For **video**, the server resolves direct links using a fallback chain:
   - **Direct file** — if the URL already points at a video file (`.mp4`, `.webm`, …), it is validated and returned as-is.
   - **yt-dlp** — the primary extractor for supported sites.
   - **Generic extractor** — yt-dlp's `force_generic_extractor` pass.
   - **HTML scrape** — regex search of the page HTML for `.mp4`/`.webm`/`.m3u8` URLs.
   Each candidate link is then **probed**, and only confirmed-dead ones
   (404/410 or an HTML error page) are dropped — uncertain links are kept.
4. For **images/galleries**, the server shells out to `gallery-dl` to list
   every image (and any video items) on the page — no files are downloaded
   server-side, just their URLs and metadata.
5. Results are grouped by quality/format (video) or by source page
   (gallery) and shown as cards. The full video quality ladder is returned,
   including high-res adaptive streams that have no audio (flagged
   **"video only"**).
6. The client builds a **proxied URL** per format/image (pointing at the
   backend's `GET /proxy-video`), which replays the request to the source
   with the right Referer/Cookie/User-Agent (impersonating a browser) and
   rewrites HLS playlists. A per-card toggle lets you play/download direct
   or via the proxy.
7. If a video has no existing captions, you can hit **Generate subtitles**:
   the server downloads just the audio, runs it through Groq's Whisper
   speech-to-text API, and hands back a subtitle track (`.vtt`/`.srt`) plus a
   small waveform preview for the seek bar. This needs a free
   [Groq API key](https://console.groq.com) — see `GROQ_API_KEY` below.

## Features

- Direct-link extraction from arbitrary pages via yt-dlp + scraping fallbacks.
  By default only qualities that play **with sound** are shown; YouTube's high-res
  streams are video-only (audio is a separate file that browsers can't merge), so
  they're hidden behind a "Show video-only qualities" preference and flagged
  "video only" when enabled.
- Image/gallery extraction (Instagram, X/Twitter, and anything else
  [gallery-dl](https://github.com/mikf/gallery-dl) supports) with a lightbox
  viewer, per-image download, and copy-all.
- **Auto/manual content-type detection** — auto mode (default) tries video
  then falls back to gallery automatically; force one explicitly from
  Preferences if you know which a page is.
- Auto-generated subtitles (speech-to-text via Groq Whisper) for videos with
  no existing captions, with a waveform-backed seek bar.
- Built-in player ([Video.js v10](https://videojs.org) — `@videojs/html` with its
  **minimal** skin and the hls.js engine) — responsive controls and a unified
  quality menu.
- Streaming media proxy: HLS playlist rewriting, Range/seek, header passthrough,
  and browser impersonation so anti-bot CDNs still play.
- Browser-impersonating extraction (curl_cffi) to beat 403/410 anti-bot blocks,
  plus link validation that hides confirmed-dead formats.
- Per-format download + copy, batch extraction, search/filter, QR hand-off.
- Server-side TTL result cache plus a client-side cache, so repeats are instant.
- Results and preferences persisted in `localStorage`.
- Bilingual UI (English / فارسی) with full RTL mirroring; backend and extractor
  error messages stay in English.
- Light / dark / system themes plus compact and reduced-motion modes.

## Project layout

```
.
├── client/    # SvelteKit static SPA (UI only)
├── server/    # FastAPI backend: video/gallery extraction, proxy, transcription
├── deploy/    # Ready-made configs + scripts for every hosting option
├── docs/      # ARCHITECTURE.md — a technical map for engineers
└── archive/   # Design notes for removed/experimental features (e.g. OVC)
```

For a deeper technical walkthrough of how the pieces fit together (request
flows, the extraction fallback chain, the proxy, the subtitles pipeline),
see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Prerequisites

- Node.js 22+ and npm (to build the client)
- Python 3.10+
- [ffmpeg](https://ffmpeg.org) on `PATH` — only needed for auto-subtitles
  (`/transcribe`); normal link extraction doesn't use it at all, so a
  missing/broken install stays invisible until someone actually generates
  subtitles. Check `GET /health`'s `ffmpegAvailable` field if unsure.

## Setup

### 0. Get the code

```bash
git clone https://github.com/MEOWBEY/direct-stream.git
cd direct-stream
```

### 1. Server (FastAPI)

```bash
cd server
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit as needed
python run.py                 # serves on http://localhost:8000
# or: uvicorn app.main:app --reload
```

The server is a package under `server/app/`:

| Module | What it does |
| --- | --- |
| `main.py` | FastAPI app + all routes |
| `config.py` | `Settings` — every environment variable, in one place |
| `models.py` / `serializers.py` | Internal + wire (client-facing) data shapes, and the mapping between them |
| `extractor.py` | Video extraction (yt-dlp + generic + HTML-scrape fallback chain, error classification) |
| `gallery.py` | Image/gallery extraction (gallery-dl subprocess) |
| `proxy.py` | The streaming media proxy (`GET /proxy-video`) |
| `net_common.py` | Shared cookie/impersonation helpers used by both extractors |
| `cache.py` | The in-memory TTL result cache |
| `jobs.py` | The auto-subtitles job pipeline/state machine |
| `audio.py` | Audio acquisition + ffmpeg extraction for transcription |
| `waveform.py` | Waveform peak extraction for the player's seek bar |
| `subtitles.py` | Subtitle segment merging + `.vtt`/`.srt` generation |
| `transcribe/` | The Groq Whisper transcription engine |
| `logging_context.py` | Request-scoped logging (client IP/user-agent on every log line) |

### 2. Client (SvelteKit static SPA)

```bash
cd client
npm install
npm run dev                   # serves on http://localhost:5173
```

In dev, leave `VITE_API_BASE_URL` unset — Vite's dev proxy forwards the backend
routes to `http://localhost:8000` (no CORS). Open http://localhost:5173.

## API

All responses are JSON. Successful responses have `"success": true`; errors
return `"success": false` with an `"error"` message (and the matching HTTP
status code — 400/401/403/404/422/429/451/502/504 depending on what went
wrong).

### `POST /extract-videos`

Request:
```json
{ "url": "https://example.com/watch?v=abc123", "cookies": null }
```

Response:
```json
{
  "success": true,
  "video": {
    "metadata": { "id": "abc123", "title": "Example video", "duration": 125.4 },
    "formats": [
      {
        "formatId": "137",
        "resolution": 1080,
        "ext": "mp4",
        "protocol": "https",
        "sourceVideoUrl": "https://cdn.example.com/...",
        "httpHeaders": { "Referer": "https://example.com/" },
        "videoOnly": true
      }
    ],
    "subtitleTracks": []
  },
  "method": "yt-dlp",
  "cached": false
}
```

`cookies` is optional — a Netscape `cookies.txt` blob or a single
`Cookie: a=b; c=d` line, from the app's **Settings → Cookies** panel.

### `POST /extract-gallery`

Request/response shape mirrors `/extract-videos`, wrapped under `"gallery"`
instead of `"video"`:
```json
{
  "success": true,
  "gallery": {
    "title": "A carousel post",
    "webpageUrl": "https://instagram.com/p/xyz/",
    "images": [
      { "url": "https://scontent.cdninstagram.com/...", "width": 1080, "height": 1350, "ext": "jpg" }
    ],
    "skippedCount": 0
  },
  "method": "gallery-dl",
  "cached": false
}
```

`skippedCount` is how many items `gallery-dl` reported as errors or in a
shape this app doesn't recognize — a non-zero value means the gallery is
partial (common on Instagram/X without fresh cookies), not necessarily a bug.

### `GET /proxy-video`

Streams media through the server with the right Referer/Cookie/User-Agent
injected. Called by the player/downloader with query params built by the
client — you shouldn't need to construct this URL by hand.

```
GET /proxy-video?url=https%3A%2F%2Fcdn.example.com%2Fvid.mp4&protocol=https&referer=https%3A%2F%2Fexample.com
```

### `POST /transcribe`, `GET /transcribe/{jobId}`

Kicks off auto-subtitles for a video, then poll for progress:

```json
// POST /transcribe
{ "webpageUrl": "https://example.com/watch?v=abc123", "formats": [ /* the video's own formats array */ ] }
// -> { "jobId": "3f9a..." }

// GET /transcribe/3f9a...
{
  "jobId": "3f9a...",
  "status": "transcribing",
  "progress": 0.42,
  "stepLabel": "Transcribing…"
}
// once status is "done":
{
  "jobId": "3f9a...",
  "status": "done",
  "progress": 1,
  "stepLabel": "Done",
  "result": {
    "language": "en",
    "vttUrl": "/transcribe/3f9a.../subtitle.vtt",
    "srtUrl": "/transcribe/3f9a.../subtitle.srt",
    "waveform": [0.1, 0.4, 0.35, ...]
  }
}
```

Responds `503` if `GROQ_API_KEY` isn't set (the feature is simply disabled,
not broken).

### `GET /health`

```json
{
  "status": "healthy",
  "service": "directstream",
  "version": "3.0.0",
  "timestamp": "2026-07-08T12:00:00+00:00",
  "ffmpegAvailable": true,
  "galleryDlAvailable": true
}
```

`ffmpegAvailable`/`galleryDlAvailable` being `false` means auto-subtitles or
gallery extraction will fail — see the env var notes below for how to fix
either.

## Environment variables

### Server (`server/.env`)

| Variable | Default | Description |
| --- | --- | --- |
| `DEBUG` | `false` | Enables FastAPI debug + autoreload. |
| `LOG_LEVEL` | `INFO` | Python log level. |
| `HOST` / `PORT` / `WORKERS` | `0.0.0.0` / `8000` / `1` | Only used when running via `python run.py` directly. Behind gunicorn/systemd (see `deploy/`), the actual bind address comes from the systemd unit, not these. |
| `CORS_ORIGINS` | `*` | Comma-separated allowed origins (set to the client origin in prod). |
| `CLIENT_DIR` | _(empty)_ | Combined single-process deploy only: path to the built static client (`client/build`) to serve from the same origin. Leave empty for a split deploy. |
| `MAX_FORMATS` | `40` | Max formats returned per extraction. |
| `REQUEST_TIMEOUT` | `90` | Per-extraction timeout (seconds). |
| `MAX_RETRIES` | `2` | yt-dlp retry count. |
| `SCRAPE_MAX_BYTES` | `200000` | Cap on page bytes read for the HTML-scrape fallback. |
| `EXTRACT_WORKERS` | `4` | Thread-pool size for blocking yt-dlp work. |
| `ENABLE_IMPERSONATION` | `true` | curl_cffi browser impersonation (extraction **and** proxy) — bypasses anti-bot 403/410. |
| `IMPERSONATE_CLIENT` | `chrome` | Browser fingerprint to impersonate (`chrome`, `safari`, `edge`, …). |
| `VALIDATE_FORMATS` | `true` | Probe links and hide only confirmed-dead ones (404/410/HTML page). |
| `CACHE_TTL` | `300` | Result cache time-to-live (seconds, `0` disables). |
| `CACHE_MAX_ENTRIES` | `512` | Max entries kept in the in-memory result cache. |
| `COOKIE_FILE` | _(empty)_ | Server-side default Netscape `cookies.txt` path(s), comma-separated for several accounts (fallback when a request brings no cookies). Requests rotate across the accounts; one that hits a rate limit / bot flag rests 5 minutes while the others keep serving. Unlocks age-restricted / private / login-gated content. |
| `PROXY_URL` | _(empty)_ | Outbound proxy (`http(s)://…` / `socks5://…`) for extraction, probing **and** media streaming. Routes around datacenter-IP blocks/rate-limits. |
| `YOUTUBE_PLAYER_CLIENTS` | _(empty)_ | Comma list of YouTube player clients (e.g. `default,tv,web_safari`). Keep `default` to preserve the full quality ladder; add age-gate-capable clients. |
| `YOUTUBE_PO_TOKEN` | _(empty)_ | Comma-separated PO token(s) to clear YouTube bot-detection on datacenter IPs. Manually-copied tokens go stale almost immediately (YouTube binds them to a specific video ID) — the [VPS installer](deploy/server/vps/) sets up an automatic PO-token-provider service instead, which is what you want on a real deploy. |
| `SLEEP_REQUESTS` | `0` | Seconds to sleep between extractor requests — `1`–`3` cuts 429/"used too much" blocks under load. |
| `GALLERY_DL_BINARY` | `gallery-dl` | gallery-dl invocation. The default runs it via `python -m gallery_dl` (avoids PATH issues with pip-installed console scripts); point this at a custom wrapper only if you need something else. |
| `GALLERY_DL_TIMEOUT` | `45` | Per-extraction timeout for gallery-dl (seconds). |
| `GALLERY_DL_WORKERS` | `3` | Thread-pool size for gallery-dl subprocess calls. |
| `FFMPEG_BINARY` / `FFPROBE_BINARY` | `ffmpeg` / `ffprobe` | Only used by auto-subtitles (`/transcribe`) and its waveform preview. Set to an absolute path (e.g. `/usr/bin/ffmpeg`) if it's installed somewhere not on this process's PATH — check `GET /health`'s `ffmpegAvailable` field if you're not sure. |
| `GROQ_API_KEY` | _(empty)_ | Free key from [console.groq.com](https://console.groq.com), no card required. Empty disables `/transcribe` (503 instead of failing mid-job). Accepts several comma-separated keys — requests spread across the pool, a rate-limited key cools down while the job instantly retries on another, and chunk parallelism scales with pool size (5 per key, capped at 16). |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | Which Groq Whisper model to transcribe with. |
| `TRANSCRIBE_ENABLED` | `true` | Turns the whole `/transcribe` feature off without touching `GROQ_API_KEY`. |
| `TRANSCRIBE_MAX_CONCURRENT_JOBS` | `2` | Concurrent transcription jobs across all clients — each pins Groq + local ffmpeg CPU work. |
| `TRANSCRIBE_MAX_DOWNLOAD_BYTES` | `300000000` | Hard cap on the one audio/video stream a job downloads to disk (~300MB). |
| `TRANSCRIBE_JOB_TTL` | `1800` | How long a finished job's result/subtitle files stay downloadable before being swept from memory. |
| `TRANSCRIBE_WORKERS` | `2` | Thread/subprocess pool size for the ffmpeg extraction/chunking step. |

> **Authentication & blocks.** Age-restricted, private, and most Instagram/X
> content require cookies. Set a server-side default with `COOKIE_FILE`, and/or
> let each user paste their own per-site cookies in the app's **Settings →
> Cookies** panel (stored only in their browser, sent per-request). YouTube
> also frequently blocks datacenter/VPS IPs outright ("Sign in to confirm
> you're not a bot") regardless of cookies — that needs a PO token, which the
> [VPS installer](deploy/server/vps/) sets up an automatic provider service
> for; see its **YouTube PO tokens** section for what that is and why.

### Client (`client/.env`)

| Variable            | Default   | Description                                                                                                            |
| ------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL` | _(empty)_ | Backend origin for a deployed static build (e.g. `https://api.example.com`). Leave empty in dev to use the Vite proxy. |

## Build & deploy

```bash
cd client
VITE_API_BASE_URL=https://api.example.com npm run build   # -> build/ static files
npm run preview                                           # preview locally
```

Deploy `client/build/` to any static host (CDN, nginx, etc.) and run the Python
server somewhere reachable at `VITE_API_BASE_URL`. Set the server's
`CORS_ORIGINS` to the client's origin.

For ready-made configs and step-by-step guides — Docker, Railway, Render,
Fly.io, Vercel, Netlify, Cloudflare Pages, Deno Deploy, and a full personal
VPS — see [`deploy/`](deploy/). The VPS path in particular has an
**interactive `install.sh`** that sets up the backend and (if you want) the
client together by asking a few plain-language questions (domain, port, how
to serve the client) — see [`deploy/server/vps/`](deploy/server/vps/).

## Security note

The proxy (`GET /proxy-video`) fetches arbitrary user-supplied URLs without a
host allow-list, so a public deployment is exposed to SSRF-style abuse. Run it
locally, or add an allow-list / network egress controls before exposing it.

> A previous **OVC** (headless-browser resolver) mode was removed in favor of the
> impersonating proxy. Its design is preserved in [`archive/OVC.md`](archive/OVC.md) in
> case it needs reviving.

## Known issues

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for a plain-language list of
what's broken or still rough around the edges.

## Tech stack

- **Client:** SvelteKit (`adapter-static`, SPA), Svelte 5 (runes), Tailwind CSS 4,
  bits-ui / shadcn-svelte components, Video.js v10 (`@videojs/html`) + hls.js, a
  lightweight runes-based i18n layer (English / Farsi).
- **Server:** FastAPI, yt-dlp, gallery-dl, curl_cffi (impersonation), httpx
  (async), uvicorn, pydantic-settings, Groq (Whisper speech-to-text).
