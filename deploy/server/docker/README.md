# Docker (single-process image)

The one artifact every container-based platform in this repo builds from:
`Dockerfile` here bundles the built SvelteKit client **and** the FastAPI
backend into one image, so one process/one port serves everything from the
same origin (no CORS to configure). It's an *option*, not the only path —
Railway and Render can also run the backend and client natively without
Docker (see [`../railway/`](../railway/) Option B and
[`../../client/render/`](../../client/render/)); this is the portable
fallback that works identically everywhere, including your own hardware.

Used directly by:
- [`../railway/`](../railway/) Option A
- [`../render/`](../render/)
- [`../flyio/`](../flyio/) (Fly always builds a container, so this is the
  only path there)
- [`../vps/`](../vps/), via `docker-compose.yml` here, if you'd rather run
  Docker on your own box than a native systemd service

## Install

You need Docker (or Docker Desktop on Windows/Mac) with Compose v2:

```bash
docker --version
docker compose version
```

## Build & run locally

From the **repo root** (the build needs both `client/` and `server/`):

```bash
cp server/.env.example server/.env    # edit as needed
docker build -f deploy/server/docker/Dockerfile -t directstream .
docker run -p 8000:8000 --env-file server/.env directstream
```

Open http://localhost:8000 — the built client and the API are both served
from there.

## Build args

| Arg                   | Default | Purpose                                                                                  |
| ---------------------- | ------- | ----------------------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`    | _(empty)_ | Leave empty for single-process/same-origin deploys. Set it only if this image's client should call a *different* origin (split-deploy). |

```bash
docker build -f deploy/server/docker/Dockerfile \
  --build-arg VITE_API_BASE_URL=https://api.example.com \
  -t directstream .
```

## Run with Compose (adds a reverse proxy + automatic HTTPS)

`docker-compose.yml` here adds Caddy in front of the app for TLS — see
[`../vps/`](../vps/) for the full personal-server walkthrough. Quick local
version:

```bash
DOMAIN=localhost docker compose -f deploy/server/docker/docker-compose.yml up -d --build
```

## Notes

- The image installs `ffmpeg` and `curl` (curl only for the container
  `HEALTHCHECK`); no other system packages are needed.
- Runs as a non-root `appuser` inside the container.
- `HEALTHCHECK` hits `GET /health` — used by Docker itself and by platforms
  (Railway/Render/Fly) that read container health status.
