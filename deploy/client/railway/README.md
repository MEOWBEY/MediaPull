# Deploy the client to Railway (static site, no Docker)

Runs the built SvelteKit SPA as its own Railway service, separate from the
backend. Pair with [`../../server/railway/`](../../server/railway/) Option B
(or any other backend host) for a fully split deploy.

## Setup

1. **Install**: push this repo to GitHub.
2. In Railway: **New Project → Deploy from GitHub repo** → select this repo
   (or **New Service** in an existing project, if the backend already lives
   there).
3. **Settings → Source** → set **Root Directory** to `client`.
4. Copy `deploy/client/railway/Procfile` to `client/Procfile`. Nixpacks
   auto-detects the Node app from `package.json`; the Procfile just defines
   the start command:
   ```
   web: npm run build && npx serve -s build -l $PORT
   ```
   `serve -s` serves the static build with single-page-app routing (all
   unmatched paths fall back to `index.html`), matching what
   `adapter-static`'s `fallback: 'index.html'` produces.
5. **Variables** → set `VITE_API_BASE_URL` to your backend's public URL
   (e.g. `https://directstream-api.up.railway.app`). This must be set
   **before/at build time** — Vite bakes it into the static bundle, it isn't
   read at runtime.
6. **Settings → Networking** → generate a domain (or attach a custom one).
7. On the backend service, set `CORS_ORIGINS` to this client's domain.

## Notes

- If you'd rather not run two Railway services, use the combined Docker
  option in [`../../server/docker/`](../../server/docker/) or
  [`../../server/railway/`](../../server/railway/) Option A instead — one
  service serves both API and client from the same origin, no CORS wiring
  needed at all.
