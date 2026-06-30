# DirectStream

Extract direct video links from any webpage, then preview them in a built-in
player, download them, or stream them through an optional proxy.

DirectStream is a static web client backed by a single Python service:

- **Client** — a SvelteKit **static SPA** (UI, in-browser HLS player, result
  management). No server runtime: it builds to plain static files.
- **Server** — a Python FastAPI service that does everything backend: link
  extraction with [yt-dlp](https://github.com/yt-dlp/yt-dlp) (+ generic and
  HTML-scrape fallbacks) using browser impersonation to beat anti-bot blocks,
  and a streaming media **proxy** (with HLS rewriting and Range support) that
  also impersonates so blocked CDNs still play.

> For educational use. You are responsible for complying with the terms of
> service of any site you point it at and with applicable copyright law.

## How it works

1. You paste a webpage URL in the client.
2. The client calls the backend's `POST /extract-videos`.
3. The server resolves direct video links using a fallback chain:
   - **Direct file** — if the URL already points at a video file (`.mp4`, `.webm`, …), it is validated and returned as-is.
   - **yt-dlp** — the primary extractor for supported sites.
   - **Generic extractor** — yt-dlp's `force_generic_extractor` pass.
   - **HTML scrape** — regex search of the page HTML for `.mp4`/`.webm`/`.m3u8` URLs.
4. Each candidate link is **probed** and only confirmed-dead ones (404/410 or an
   HTML error page) are dropped — uncertain links are kept.
5. Results are grouped by quality/format and shown as cards. The full quality
   ladder is returned, including high-res adaptive streams that have no audio
   (flagged **"video only"**).
6. The client builds a **proxied URL** per format (pointing at the backend's
   `GET /proxy-video`), which replays the request to the source with the right
   Referer/Cookie/User-Agent (impersonating a browser) and rewrites HLS
   playlists. A per-card toggle lets you play/download direct or via the proxy.

## Features

- Direct-link extraction from arbitrary pages via yt-dlp + scraping fallbacks.
  By default only qualities that play **with sound** are shown; YouTube's high-res
  streams are video-only (audio is a separate file that browsers can't merge), so
  they're hidden behind a "Show video-only qualities" preference and flagged
  "video only" when enabled.
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
├── client/   # SvelteKit static SPA (UI only)
└── server/   # FastAPI backend: extract + proxy
```

## Prerequisites

- Node.js 18+ and npm (to build the client)
- Python 3.10+

## Setup

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

The server is a package under `server/app/` (`config`, `models`, `serializers`,
`cache`, `extractor`, `proxy`, `main`). It exposes `POST /extract-videos`,
`GET /proxy-video`, and `GET /health`.

### 2. Client (SvelteKit static SPA)

```bash
cd client
npm install
npm run dev                   # serves on http://localhost:5173
```

In dev, leave `VITE_API_BASE_URL` unset — Vite's dev proxy forwards the backend
routes to `http://localhost:8000` (no CORS). Open http://localhost:5173.

## Environment variables

### Server (`server/.env`)

| Variable               | Default     | Description                                                               |
| ---------------------- | ----------- | ------------------------------------------------------------------------- |
| `DEBUG`                | `false`     | Enables FastAPI debug + autoreload.                                       |
| `LOG_LEVEL`            | `INFO`      | Python log level.                                                         |
| `CORS_ORIGINS`         | `*`         | Comma-separated allowed origins (set to the client origin in prod).       |
| `MAX_FORMATS`          | `40`        | Max formats returned per extraction.                                      |
| `ENABLE_IMPERSONATION` | `true`      | curl_cffi browser impersonation (extraction **and** proxy) — bypasses anti-bot 403/410. |
| `IMPERSONATE_CLIENT`   | `chrome`    | Browser fingerprint to impersonate (`chrome`, `safari`, `edge`, …).       |
| `VALIDATE_FORMATS`     | `true`      | Probe links and hide only confirmed-dead ones (404/410/HTML page).        |
| `REQUEST_TIMEOUT`      | `90`        | Per-extraction timeout (seconds).                                         |
| `EXTRACT_WORKERS`      | `4`         | Thread-pool size for blocking yt-dlp work.                                |
| `CACHE_TTL`            | `300`       | Result cache time-to-live (seconds, `0` disables).                        |
| `PORT`                 | `8000`      | Server port.                                                              |
| `COOKIE_FILE`          | _(empty)_   | Path to a server-side default Netscape `cookies.txt` (fallback when a request brings no cookies). Unlocks age-restricted / private / login-gated content. |
| `PROXY_URL`            | _(empty)_   | Outbound proxy (`http(s)://…` / `socks5://…`) for extraction, probing **and** media streaming. Routes around datacenter-IP blocks/rate-limits. |
| `YOUTUBE_PLAYER_CLIENTS` | _(empty)_ | Comma list of YouTube player clients (e.g. `default,tv,web_safari`). Keep `default` to preserve the full quality ladder; add age-gate-capable clients. |
| `YOUTUBE_PO_TOKEN`     | _(empty)_   | Comma-separated PO token(s) to clear YouTube bot-detection on datacenter IPs (usually from a bgutil PO-token sidecar). |
| `SLEEP_REQUESTS`       | `0`         | Seconds to sleep between extractor requests — `1`–`3` cuts 429/"used too much" blocks under load. |

> **Authentication & blocks.** Age-restricted, private, and most Instagram
> content require cookies. Set a server-side default with `COOKIE_FILE`, and/or
> let each user paste their own per-site cookies in the app's **Settings →
> Cookies** panel (stored only in their browser, sent per-request). For YouTube
> on a server, also install a JS runtime (Deno/Node) so yt-dlp can solve the
> n-challenge — see [`deploy/`](deploy/).

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

## Security note

The proxy (`GET /proxy-video`) fetches arbitrary user-supplied URLs without a
host allow-list, so a public deployment is exposed to SSRF-style abuse. Run it
locally, or add an allow-list / network egress controls before exposing it.

> A previous **OVC** (headless-browser resolver) mode was removed in favor of the
> impersonating proxy. Its design is preserved in [`docs/OVC.md`](docs/OVC.md) in
> case it needs reviving.

## Tech stack

- **Client:** SvelteKit (`adapter-static`, SPA), Svelte 5 (runes), Tailwind CSS 4,
  bits-ui / shadcn-svelte components, Video.js v10 (`@videojs/html`) + hls.js, a
  lightweight runes-based i18n layer (English / Farsi).
- **Server:** FastAPI, yt-dlp, curl_cffi (impersonation), httpx (async), uvicorn,
  pydantic-settings.
