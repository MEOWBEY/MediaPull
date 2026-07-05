# Deploy the client to Vercel (static, client only)

Vercel hosts the built SvelteKit SPA. It **cannot** run the Python backend —
Vercel's serverless/edge functions don't support long-running processes or
arbitrary system binaries like `ffmpeg`/`yt-dlp` invoked as subprocesses.
Deploy the backend separately (any of [`../../server/`](../../server/)) and
point this client at it.

## Install

```bash
npm i -g vercel   # optional — dashboard/GitHub-integration works without the CLI
```

## Setup — via dashboard (recommended)

1. Push this repo to GitHub.
2. In Vercel: **Add New → Project**, import this repo.
3. This file (`vercel.json`) needs to live at the **repo root** for Vercel
   to pick it up automatically (Vercel's project "Root Directory" defaults
   to the repo root, matching this file's `cd client &&` build command):
   ```bash
   cp deploy/client/vercel/vercel.json ./vercel.json
   ```
4. **Settings → Environment Variables** → add `VITE_API_BASE_URL` =
   your backend's public URL (e.g. `https://directstream-api.onrender.com`).
   This is a **build-time** variable (Vite bakes it into the bundle) — set
   it before the first deploy, and redeploy after changing it.
5. Deploy. Vercel runs `cd client && npm ci && npm run build` and serves
   `client/build`, with the `rewrites` rule sending unmatched paths to
   `index.html` (required for client-side routing).
6. On the backend, set `CORS_ORIGINS` to the Vercel domain Vercel assigns
   you (or your custom domain, once attached in **Settings → Domains** —
   Vercel issues the TLS cert automatically).

## Setup — via CLI (alternative)

```bash
cp deploy/client/vercel/vercel.json ./vercel.json
vercel link
vercel env add VITE_API_BASE_URL production   # paste your backend URL
vercel --prod
```

## Notes

- If you'd rather not touch the repo root, use **Netlify**
  ([`../netlify/`](../netlify/)) instead — its config supports a `base`
  directory natively.
