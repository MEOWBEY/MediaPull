# Deploy the backend to Northflank

As of 2026, Northflank's free ("Developer sandbox") tier is one of the few
that gives you a genuinely **always-on** container — 2 free services, no
idle spin-down, no credit-card-required trial clock like Fly.io. Good
default choice if Railway's trial credit and Render's spin-down aren't what
you want, and you don't want to run your own VPS.

Builds `deploy/server/docker/Dockerfile` — same single-process image
(API + built client together) used by Railway/Render/Fly, so this doubles
as a combined deploy with no separate client host needed. For a split
deploy, add the `VITE_API_BASE_URL` build argument (step 5 below) and host
the client on Vercel/Netlify/Cloudflare Pages instead.

## Setup

1. **Install**: push this repo to GitHub (Northflank deploys from a
   connected git repo; no CLI required for this flow).
2. Sign up at northflank.com, then **Create → Service → Combined
   service** (or **Deployment**, depending on current UI naming) →
   **Add from Git repository** → select this repo.
3. **Build settings**:
   - **Build type**: Dockerfile
   - **Dockerfile path**: `deploy/server/docker/Dockerfile`
   - **Build context**: `/` (repo root — the build needs both `client/`
     and `server/`)
4. **Networking**: add a public port on `8000`, HTTP, with a health check
   at `GET /health`. Northflank assigns a `*.northflank.app` domain
   automatically; attach a custom domain + free TLS in the service's
   **Networking → Domains** tab.
5. **Environment variables** → add what you need from
   `server/.env.production.example`, minimally `CORS_ORIGINS` set to this
   service's domain (or the separate client's domain, if split-deploying).
   If splitting, also add a **build argument** `VITE_API_BASE_URL` set to
   this service's Northflank/custom domain.
6. Deploy. Northflank builds the Dockerfile and runs the container; your
   assigned domain serves the app (API + client, if combined).

## Notes

- Free tier caps: 2 services, 2 databases, 2 cron jobs, 2 projects — plenty
  for one instance of this app, not meant for scaling multiple projects at
  once on the free plan.
- Because containers don't spin down, this is a better fit than Render's
  free plan if you want the extraction/proxy endpoints to respond instantly
  every time rather than cold-starting after idle periods.
