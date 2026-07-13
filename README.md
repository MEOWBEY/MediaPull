# pullbox

Extract video download links and image galleries from URLs — paste a link, get
downloadable files. Backed by [yt-dlp](https://github.com/yt-dlp/yt-dlp) for
video and [gallery-dl](https://github.com/mikf/gallery-dl) for images, with
optional automatic subtitle generation via Groq Whisper.

## Quick start

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-org/pullbox.git
cd pullbox
```

**Server** (Python 3.10+):

```bash
cd server
pip install -r requirements.txt
cp .env.example .env        # edit .env — at minimum set a SECRET_KEY
```

**Client** (Node.js 18+):

```bash
cd client
npm install
npm run build
```

### 2. Run

```bash
# Terminal 1 — backend
cd server
python -m app

# Terminal 2 — frontend (or serve the build/ directory via nginx/etc.)
cd client
npm run dev
```

The frontend runs on `http://localhost:5173` by default and expects the backend
at `http://localhost:8000` (both configurable).

### 3. Use it

Paste a URL into the input field. The backend extracts download links for
videos (qualities, formats) or image galleries. Click a result to download.

Set cookies in **Settings → Cookies** for sites that require authentication
(e.g. Instagram, Twitter).

Optional subtitle generation: configure `GROQ_API_KEY` in `server/.env` and
enable **Subtitles** in the UI.

## How it works

```
browser ──▶ SvelteKit client ──▶ FastAPI backend ──▶ yt-dlp / gallery-dl
                    │                    │
                    │                    ├─ /extract-videos, /extract-gallery  (link extraction)
                    │                    ├─ /proxy-video    (streams media with the right headers)
                    │                    ├─ /proxy-token    (swaps auth cookies for an opaque token)
                    └────────────────────┴─ /transcribe     (optional Groq Whisper subtitles)
```

- The client never talks to source sites directly — the backend extracts links
  and (optionally) proxies the media, injecting the Referer/Cookie/User-Agent a
  browser can't set on a `<video>` element.
- State is in-memory and per-process (result cache, transcription jobs, proxy
  cookie tokens), so the backend runs **single-worker** — scale out with more
  instances behind a load balancer, not more workers.
- Auth cookies are exchanged for a short-lived token before they enter any proxy
  URL, so copied/QR/shared links never leak a session.

## Documentation

- **[Server setup](server/README.md)** — backend configuration, env vars, security
- **[Client setup](client/README.md)** — frontend build, routing, dev mode
- **[Deployment](deploy/README.md)** — run it on your own VPS (systemd + nginx/Caddy)
- **[Known issues](KNOWN_ISSUES.md)** — bug-tracker style list

## License

MIT