# pullbox

**Paste a link → get the video (or a whole image gallery).** No accounts, no
installs for the person using it — just a URL in, downloadable files out.

Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) for video and
[gallery-dl](https://github.com/mikf/gallery-dl) for images, with optional
automatic subtitles via Groq Whisper.

## What it does

- **Extract video links** — paste a page URL, get every available quality and
  format, ready to preview, download, or copy.
- **Download image galleries** — pull a whole album/gallery in one go, with
  download-all.
- **Built-in player** — preview before you download; switch quality inline.
- **Auto / Video / Gallery** — leave it on **Auto** and pullbox figures out
  whether the page is a video or a gallery. Force one from the extract bar if
  you already know.
- **Optional subtitles** — generate captions for any video via speech-to-text.
- **Proxy mode** — stream media through the backend when a direct link won't
  play in the browser (wrong headers, hotlink protection).
- **Sign-in cookies** — add cookies in **Settings → Sign-in** for sites that
  need a login (Instagram, X/Twitter, etc.).
- **Mobile-first UI** — big primary actions (Download / Copy), power features
  tucked into an overflow so the phone screen stays clean.
- **Bilingual** — English and Persian (RTL-aware).

## Quick start

### 1. Install

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
2. Leave the mode on **Auto** (or pick **Video** / **Gallery**), then hit
   **Extract**.
3. Preview, then **Download** or **Copy** the link you want.
4. For login-only sites, add cookies in **Settings → Sign-in** and try again —
   the error banner has a one-tap shortcut to that panel.

Want subtitles? Set `GROQ_API_KEY` in `server/.env`, then use the **Subtitles**
button on any video card.

## How it works

Your browser only ever talks to the pullbox backend — never to the source site
directly. The backend does the extracting (and optional proxying), because it
can send the `Referer` / `Cookie` / `User-Agent` headers a plain `<video>` tag
can't.

```
                 ┌──────────────────────── FastAPI backend ────────────────────────┐
 browser ──▶ SvelteKit client ──▶  /extract-videos   ──▶ yt-dlp        (video links)
                                   /extract-gallery   ──▶ gallery-dl    (image lists)
                                   /proxy-video       ──▶ media + real browser headers
                                   /proxy-token       ──▶ cookies → opaque `ctok`
                                   /transcribe        ──▶ Groq Whisper  (optional subs)
                 └─────────────────────────────────────────────────────────────────┘
```

**Two things worth knowing:**

- **Cookies never leak.** Auth cookies are swapped for a short-lived token
  (`ctok`) *before* they ever appear in a proxy URL, so a copied / QR'd / shared
  link can't expose your session.
- **Single-worker by design.** The result cache, transcription jobs, and proxy
  tokens all live in-memory per process — scale out with more *instances* behind
  a load balancer, not more workers.

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
- **[Deployment](deploy/README.md)** — run it on your own VPS (systemd + nginx/Caddy)
- **[Known issues](KNOWN_ISSUES.md)** — bug-tracker style list
- **[Plans](plans/README.md)** — improvement / production roadmap

## Production notes

- Pin `CORS_ORIGINS` to your real frontend origin(s) (not `*`) if you need
  credentialed cross-origin requests.
- On a public VPS, set `PROXY_ALLOWED_HOSTS` to known media CDNs so the media
  proxy isn't an open relay.
- Keep `yt-dlp` updated when YouTube extraction breaks (`pip install -U yt-dlp`).

## License

MIT
