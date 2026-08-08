# MediaPull client

Svelte 5 frontend for **MediaPull**. Paste a URL, get downloadable video
formats and image galleries — preview, download, copy, optional subtitles.

## Setup

```bash
npm install        # Node 18+
cp .env.example .env   # leave VITE_API_BASE_URL empty for local dev
npm run dev        # http://localhost:5173
```

In dev, Vite proxies `/extract-*`, `/proxy-video`, `/proxy-token`, `/health`,
`/split-audio`, and `/transcribe` to the backend (`http://localhost:8000` by
default).

## Build for production

```bash
npm run build      # → build/ directory
```

Serve `build/` with any static file server (nginx, `python -m http.server`,
`npx serve`, etc.), or let the FastAPI app serve `client/build` same-origin.

## Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | *(empty)* | Backend origin. Empty in dev → relative URLs + Vite proxy. Set for split/static deploys (e.g. `https://api.example.com`). |

All other settings (sign-in cookies, playback, layout/sort, content-type,
theme, language) live in browser localStorage and are organized into tabs in
the Settings panel: **General / Library / Playback / Sign-in**.

## Scripts

```bash
npm run check   # svelte-check / types
npm run lint    # eslint
npm test        # vitest
npm run build   # production build
```
