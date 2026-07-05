# Deploy the client to Render (Static Site, no Docker)

Render has a first-class, free "Static Site" service type — the natural fit
for this SvelteKit build (`adapter-static`, plain HTML/CSS/JS output).

## Setup

1. **Install**: push this repo to GitHub/GitLab.
2. **Setup**: in Render, **New → Blueprint**, point it at this repo.
   `render.yaml` at the repo root wins by default, so either:
   - Copy this file there: `cp deploy/client/render/render.yaml ./render.yaml`
     (rename if you already have a backend `render.yaml` — Render supports
     multiple services defined in one Blueprint file; merge the `services:`
     lists if you want both in one Blueprint), or
   - Use **New → Static Site** manually instead of a Blueprint: **Root
     Directory** `client`, **Build Command** `npm ci && npm run build`,
     **Publish Directory** `build`.
3. **Environment** → set `VITE_API_BASE_URL` to your backend's URL (e.g. the
   Render/Railway/Fly.io URL from wherever you deployed
   [`../../server/`](../../server/)). This is a **build-time** variable —
   Vite bakes it into the static bundle, so re-deploy (rebuild) after
   changing it.
4. Render assigns a `*.onrender.com` URL; add a custom domain + free TLS in
   **Settings → Custom Domains**.
5. On the backend, set `CORS_ORIGINS` to this static site's domain.

## Notes

- Static sites on Render don't spin down — unlike the free "Web Service"
  plan, static hosting is always instantly available.
- The `routes: rewrite /* -> /index.html` entry is required for a
  client-routed SPA; without it, refreshing on a non-root path 404s.
