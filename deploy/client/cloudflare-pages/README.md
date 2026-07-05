# Deploy the client to Cloudflare Pages (static, client only)

Same limitation as Vercel/Netlify: Cloudflare Pages runs static assets +
optional edge Functions (Workers), not a persistent Python process with
`ffmpeg`/`yt-dlp` subprocesses. Deploy the backend separately (any of
[`../../server/`](../../server/)) and point this client at it.

The SPA fallback for client-side routing is already handled by
`client/static/_redirects` (`/* /index.html 200`), which SvelteKit copies
into the build output automatically — Cloudflare Pages reads that file
natively, no extra config needed for routing.

## Setup — via dashboard (recommended, no CLI/install needed)

1. Push this repo to GitHub.
2. Cloudflare dashboard → **Workers & Pages → Create → Pages → Connect to Git**,
   select this repo.
3. Build settings:
   - **Root directory**: `client`
   - **Build command**: `npm run build`
   - **Build output directory**: `build`
4. **Settings → Environment variables** → add `VITE_API_BASE_URL` = your
   backend's public URL, for both **Production** and **Preview**. Build-time
   variable (Vite bakes it into the bundle) — set before the first deploy.
5. Deploy. Cloudflare assigns a `*.pages.dev` domain; attach a custom domain
   in **Custom domains** (free TLS is automatic since it's already on
   Cloudflare).
6. On the backend, set `CORS_ORIGINS` to this Pages domain.

## Setup — via CLI (alternative)

```bash
npm i -g wrangler
wrangler login
cd client && npm ci && npm run build
cp ../deploy/client/cloudflare-pages/wrangler.toml ./wrangler.toml
wrangler pages deploy build --project-name=directstream-client
```

Set `VITE_API_BASE_URL` in the environment before running `npm run build`
(e.g. `VITE_API_BASE_URL=https://api.example.com npm run build`), since the
CLI path builds locally rather than on Cloudflare's build servers.
