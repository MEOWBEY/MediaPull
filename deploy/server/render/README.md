# Deploy the backend to Render

Render's **native** (buildpack) Python runtime doesn't let you install extra
system packages, and this backend needs the `ffmpeg` binary (yt-dlp uses it
for merging/remuxing formats) — so unlike Railway, there's no reliable
Docker-free path for the backend here. Use the Docker "Web Service" below.
(The **client**, on the other hand, deploys natively with zero Docker on
Render — see [`../../client/render/`](../../client/render/).)

`render.yaml` here can run either as a **backend-only** API (pair it with
`../../client/render/` or Vercel/Netlify/Cloudflare Pages for the frontend)
or as the **combined single-process** image (API + built client together,
same origin, no CORS) — same Dockerfile either way, it's just a matter of
whether you also set `VITE_API_BASE_URL` at build time.

## Setup

1. **Install**: push this repo to GitHub or GitLab.
2. **Setup**: in Render, **New → Blueprint**, point it at this repo.
   Render looks for `render.yaml` at the repo root, so either:
   - Copy it there: `cp deploy/server/render/render.yaml ./render.yaml`, or
   - Use **New → Web Service** manually (skip the Blueprint) and set
     **Runtime** to `Docker`, **Dockerfile Path** to
     `deploy/server/docker/Dockerfile`, **Docker Build Context Directory**
     to `.` (repo root).
3. Render assigns a `*.onrender.com` URL automatically. Custom domains +
   free TLS are available in **Settings → Custom Domains**.
4. **Environment** → set `CORS_ORIGINS` to wherever the client is hosted
   (its own domain, or this same Render URL if you're doing the combined
   single-process deploy) instead of leaving it at `*`.
5. If splitting the client out, add a build arg
   `VITE_API_BASE_URL=https://<this-service>.onrender.com` to the Docker
   build (Render → service → **Environment → Docker Build Args** — or leave
   it unset for the combined single-process deploy).

## Notes

- **Free plan spins down after ~15 minutes of inactivity** and takes 30–60s
  to cold-start the next request. Fine for personal/occasional use;
  annoying if you want it always warm — in that case use Fly.io
  ([`../flyio/`](../flyio/)), a paid Render instance, or your own VPS
  ([`../vps/`](../vps/)).
