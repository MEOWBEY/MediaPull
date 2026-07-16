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
cp .env.example .env        # optional: CORS_ORIGINS, GROQ_API_KEY, COOKIE_FILE, …
```

**Client** (Node.js 18+):

```bash
cd client
npm install
cp .env.example .env        # leave VITE_API_BASE_URL empty in dev (Vite proxies)
npm run build               # production static build → client/build
```

### 2. Run

```bash
# Terminal 1 — backend
cd server
uvicorn app.main:app --reload
# or: python run.py

# Terminal 2 — frontend
cd client
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies API routes to
http://localhost:8000 (including `/proxy-token`).

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
                    │                    ├─ /extract-videos, /extract-gallery
                    │                    ├─ /proxy-video    (media + headers)
                    │                    ├─ /proxy-token    (cookies → opaque ctok)
                    └────────────────────┴─ /transcribe     (optional Groq Whisper)
```

- The client never talks to source sites directly — the backend extracts links
  and (optionally) proxies the media, injecting the Referer/Cookie/User-Agent a
  browser can't set on a `<video>` element.
- State is in-memory and per-process (result cache, transcription jobs, proxy
  cookie tokens), so the backend runs **single-worker** — scale out with more
  instances behind a load balancer, not more workers.
- Auth cookies are exchanged for a short-lived token before they enter any proxy
  URL, so copied/QR/shared links never leak a session.

## Testing

```bash
# Server
cd server
ruff check app/
pytest -q

# Client
cd client
npm run check
npm run lint
npm test
```

## Documentation

- **[Server setup](server/README.md)** — backend configuration, env vars, security
- **[Client setup](client/README.md)** — frontend build, routing, dev mode
- **[Deployment](deploy/README.md)** — run it on your own VPS (systemd + nginx/Caddy)
- **[Known issues](KNOWN_ISSUES.md)** — bug-tracker style list
- **[Plans](plans/README.md)** — improve/production roadmap

## Production notes

- Pin `CORS_ORIGINS` to your real frontend origin(s) (not `*`) if you need
  credentialed cross-origin requests.
- For a public VPS, set `PROXY_ALLOWED_HOSTS` to known media CDNs so the media
  proxy is not an open relay.
- Keep `yt-dlp` updated when YouTube extraction breaks.

## License

MIT
