# Deploy the client to Netlify (static, client only)

Same limitation as Vercel: Netlify can't run the Python backend (no
persistent process, no `ffmpeg`/`yt-dlp` subprocess support). Deploy the
backend separately (any of [`../../server/`](../../server/)) and point this
client at it.

## Install

```bash
npm i -g netlify-cli   # optional — dashboard/GitHub-integration works without the CLI
```

## Setup — via dashboard (recommended)

1. Push this repo to GitHub.
2. In Netlify: **Add new site → Import an existing project**, pick this repo.
3. `netlify.toml` needs to be at the **repo root** for Netlify to read it
   automatically:
   ```bash
   cp deploy/client/netlify/netlify.toml ./netlify.toml
   ```
   Its `base = "client"` tells Netlify to build/publish from the `client/`
   subfolder without moving anything else.
4. **Site configuration → Environment variables** → add
   `VITE_API_BASE_URL` = your backend's public URL. Build-time variable
   (Vite bakes it into the bundle) — set before the first deploy, redeploy
   after changing it.
5. Deploy. Netlify runs `npm run build` inside `client/` and publishes
   `client/build`; the `[[redirects]]` rule sends unmatched paths to
   `index.html` for client-side routing.
6. Attach a custom domain in **Domain management** (free TLS is automatic),
   then set `CORS_ORIGINS` on the backend to this Netlify domain.

## Setup — via CLI (alternative)

```bash
cp deploy/client/netlify/netlify.toml ./netlify.toml
netlify init
netlify env:set VITE_API_BASE_URL https://your-backend.example.com
netlify deploy --prod
```
