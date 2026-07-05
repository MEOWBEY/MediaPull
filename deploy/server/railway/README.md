# Deploy the backend to Railway

Two ways to run the API on Railway. Pick one.

- **Option A — Docker, single process (simplest):** builds
  `deploy/server/docker/Dockerfile`, which bakes the built client in too, so
  this one service serves the whole app (API + SPA, same origin, no CORS).
- **Option B — Native Nixpacks, backend only:** no Docker; Railway's
  Nixpacks builder runs the Python app directly. Use this if you're hosting
  the client separately (Vercel/Netlify/Cloudflare Pages, or
  [`../../client/railway/`](../../client/railway/) as its own Railway
  service) and just want the API here.

Both are free-tier eligible the same way (Railway's free tier is
trial-credit based, not perpetual — see **Notes** below).

## Option A — Docker (single process)

1. **Install**: push this repo to GitHub — Railway deploys from a connected
   git repo, not a CLI upload.
2. **Setup**: in Railway, **New Project → Deploy from GitHub repo** → select
   this repo.
3. Point Railway at the Dockerfile config:
   - Copy `deploy/server/railway/railway.json` to the repo root
     (`cp deploy/server/railway/railway.json ./railway.json`), **or**
   - In the service's **Settings → Config-as-code path**, enter
     `deploy/server/railway/railway.json` (works on current Railway plans
     without moving anything).
4. **Settings → Networking** → generate a public domain (or attach your own
   custom domain — Railway issues the TLS cert automatically).
5. **Variables** → add what you need from `server/.env.example`, minimally:
   - `CORS_ORIGINS` = your Railway domain (or `*` while testing).
   - Leave `PORT` unset — Railway injects it, and `server/app/config.py`
     already reads `PORT` from the environment.
6. Deploy. Railway builds the Dockerfile and runs `python run.py`; your
   Railway URL serves both the API and the client.

## Option B — Native Nixpacks (backend only, no Docker)

1. **Install**: push this repo to GitHub.
2. **Setup**: **New Project → Deploy from GitHub repo** → select this repo.
3. In the service's **Settings → Source**, set **Root Directory** to
   `server`. Nixpacks will auto-detect the Python app from
   `requirements.txt`.
4. Copy `deploy/server/railway/nixpacks.toml` to `server/nixpacks.toml`.
   It does two things Nixpacks' default Python build won't:
   - installs `ffmpeg` (yt-dlp needs it for merging/remuxing formats), via
     `nixPkgs`;
   - sets the start command to `python run.py`.
5. **Variables** → set `CORS_ORIGINS` to wherever the client is hosted
   (its Vercel/Netlify/Cloudflare Pages/Railway URL) — required, since the
   client will be calling this API cross-origin.
6. **Settings → Networking** → generate a domain, then set that as
   `VITE_API_BASE_URL` when you build the client for its own deploy.

## Notes

- Railway's free tier is trial-credit based, not perpetual-free — check
  current pricing before depending on it long-term. For an always-on
  actually-free option, see [`../vps/`](../vps/) on a free-tier VM (e.g.
  Oracle Cloud's Always Free compute shape).
- `curl_cffi` (browser impersonation) and yt-dlp both work fine under
  Nixpacks; the only non-Python system dependency is `ffmpeg`, handled by
  `nixpacks.toml` above.
