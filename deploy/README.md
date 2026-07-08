# Deploying DirectStream

This app is two independently-deployable pieces:

- **`client/`** — a SvelteKit **static SPA** (`adapter-static`). Just HTML/CSS/JS
  once built; any static host works.
- **`server/`** — a Python **FastAPI** backend that shells out to `yt-dlp`
  and `ffmpeg` and needs a real, persistent process (not a short-lived
  serverless function).

That split is why this folder is organized the same way:

```
deploy/
├── client/     # static-hosting targets — client ONLY
│   ├── vercel/
│   ├── netlify/
│   ├── cloudflare-pages/
│   ├── deno-deploy/
│   ├── railway/          # Railway can host either piece — see below
│   └── render/
└── server/     # backend targets — server ONLY (or combined w/ client baked in)
    ├── docker/            # the single-process image every container platform builds
    ├── railway/
    ├── render/
    ├── northflank/        # genuinely-free, always-on container host
    ├── flyio/             # no ongoing free tier as of 2026 — see its README
    └── vps/               # your own server — no Docker required
```

**Some platforms genuinely can't run the backend at all**: Vercel, Netlify,
Cloudflare Pages, and Deno Deploy are all serverless/edge/static runtimes —
none of them support a persistent process invoking `ffmpeg`/`yt-dlp` as
subprocesses. That's not a config problem to work around; use them for the
client only, and host the API somewhere in `deploy/server/`.

## Two ways to run it

1. **Combined, single process** (simplest): `deploy/server/docker/` bakes
   the built client into the same image as the API, served from one origin.
   No CORS, one thing to deploy. Works on Railway, Render, Northflank,
   Fly.io, or your own VPS.
2. **Split**: client on a static host (`deploy/client/...`), backend
   elsewhere (`deploy/server/...`), talking cross-origin via
   `VITE_API_BASE_URL` (client, build-time) and `CORS_ORIGINS` (server,
   runtime). More moving parts, but lets you use free static-hosting CDNs
   for the client and pick whichever backend host suits you.

Docker is offered as **one option**, not the only one — where a platform has
a genuine native (non-Docker) path that doesn't compromise on
functionality, it's documented too (Railway's Nixpacks for the backend;
Render's, Vercel's, Netlify's, and Cloudflare Pages' native static-site
builders for the client).

## Decision matrix

| Platform | Client | Backend | Docker required? | Notes |
|---|---|---|---|---|
| [Vercel](client/vercel/) | ✅ | ❌ | No | Static only |
| [Netlify](client/netlify/) | ✅ | ❌ | No | Static only |
| [Cloudflare Pages](client/cloudflare-pages/) | ✅ | ❌ | No | Static only |
| [Deno Deploy](client/deno-deploy/) | ⚠️ possible, not recommended | ❌ never | No | Edge JS/TS runtime only — can't run Python/ffmpeg at all |
| [Railway](server/railway/) / [client](client/railway/) | ✅ (native, separate service) | ✅ (Docker **or** native Nixpacks) | Optional | Trial-credit "free" (~$5 once, then ~$1/mo) — not really always-on-free |
| [Render](server/render/) / [client](client/render/) | ✅ (native Static Site, always-on) | ✅ (Docker only — native runtime can't install `ffmpeg`) | Backend: yes. Client: no | Backend free plan spins down after ~15 min idle |
| [Northflank](server/northflank/) | ❌ (backend-focused; combined image also works) | ✅ (Docker) | Yes | **Always-on** free container, no card-gated trial clock — best "actually free" PaaS option in 2026 |
| [Fly.io](server/flyio/) | ❌ (backend-focused) | ✅ (Docker) | Yes (inherent to Fly) | **No ongoing free tier since Oct 2024** — short trial only, then pay-as-you-go (~$2–5/mo); legacy accounts grandfathered |
| [Your own VPS](server/vps/) / [client](client/vps/) | ✅ | ✅ | No (systemd + nginx/Caddy); Docker Compose offered as an alternative | Most control, works with any provider incl. free-tier VMs (e.g. Oracle Cloud Always Free — see note below) |

## Recommended paths

- **Want the least setup, one place, one URL, and it to actually be free:**
  `deploy/server/docker/` (with `CLIENT_DIR` baked in) deployed to
  **Northflank** — always-on, no spin-down, no trial clock.
- **Want it on a free static CDN + a real backend host:** client on
  Cloudflare Pages/Vercel/Netlify, backend on Northflank or Railway (native
  Nixpacks, no Docker).
- **Want full control and don't mind the setup:** a small VPS via
  `deploy/server/vps/` — one **interactive** `install.sh` sets up the
  backend AND (if you want) the client together, asking a few plain-language
  questions (domain, port, how to serve the client) instead of requiring
  you to know which env vars to set. Comes with `update.sh`/`uninstall.sh`
  for the rest of the lifecycle. Oracle Cloud's Always Free Ampere shape
  works, though Oracle quietly halved that allowance (4 OCPU/24GB → 2
  OCPU/12GB) in June 2026 with no announcement — still enough for this app,
  just no longer as generous. Any other free-tier or ~$5/mo VPS provider
  (Hetzner, DigitalOcean, etc.) works identically.
- **Avoid for the backend:** Fly.io and Railway, if "free" specifically
  matters to you — both have moved to trial-credit/pay-as-you-go models.
  They're still fine choices if you're paying or already have credits.

## Required environment variables, either way

| Where | Variable | Purpose |
|---|---|---|
| Server | `CORS_ORIGINS` | Comma-separated origins allowed to call the API. Set to the client's real domain in production — don't leave it at `*`. |
| Client (build-time) | `VITE_API_BASE_URL` | Backend origin the built client calls. Leave **unset** for combined/same-origin deploys; set it to the backend's URL for split deploys. |

See `server/.env.example` and `server/.env.production.example` for the full
list of backend knobs (cookies, proxy, YouTube player clients,
impersonation, cache, etc.) — all optional, all default to sane values.

## Security note (applies everywhere)

`GET /proxy-video` fetches arbitrary user-supplied URLs with no host
allow-list, so a public deployment is exposed to SSRF-style abuse. Run it
behind auth/a firewall/VPN, or add a host allow-list, before exposing it
broadly — see the root [`README.md`](../README.md#security-note).
