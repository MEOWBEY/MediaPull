# pullbox client

Svelte 5 frontend for pullbox. Paste a URL, get downloadable video/image
links.

## Setup

```bash
npm install        # Node 18+
cp .env.example .env   # edit API_ENDPOINT to point at your server
npm run dev        # http://localhost:5173
```

## Build for production

```bash
npm run build      # → build/ directory
```

Serve `build/` with any static file server (nginx, `python -m http.server`,
`npx serve`, etc.).

## Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_ENDPOINT` | `http://localhost:8000` | Backend URL |

All other settings (cookies, subtitles toggle, quality preference) live in
browser localStorage via the Settings panel.