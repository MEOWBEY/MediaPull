# Deno Deploy — client only, and only if you specifically want it

**The backend cannot run on Deno Deploy at all.** Deno Deploy only runs
JS/TS/WASM on an isolate-based edge runtime — no arbitrary system binaries,
no subprocess execution, no `ffmpeg`/`yt-dlp`. That rules it out
categorically for the Python backend, unlike Vercel/Netlify/Cloudflare Pages
where the limitation is "serverless functions aren't suited to this
workload" — here it's "the runtime cannot execute this at all."

For the **client**, Deno Deploy can serve static files, but it's built for
running Deno server code, not for static-site hosting — Vercel, Netlify, or
Cloudflare Pages ([`../vercel/`](../vercel/), [`../netlify/`](../netlify/),
[`../cloudflare-pages/`](../cloudflare-pages/)) will all be simpler and more
purpose-built. Use this only if you have another reason to standardize on
Deno Deploy specifically.

## Setup (static client via a tiny Deno server)

```bash
curl -fsSL https://deno.land/install.sh | sh   # install: https://docs.deno.com/runtime/manual/getting_started/installation
deno install -Arf jsr:@deno/deployctl           # install the deploy CLI
```

Build the client locally with the backend URL baked in, then deploy the
static output with a one-file static file server:

```bash
cd client
VITE_API_BASE_URL=https://your-backend.example.com npm ci && npm run build
```

Create a tiny entrypoint (not part of the repo — write it wherever you're
deploying from) that serves `build/` with SPA fallback:

```ts
// serve.ts
import { serveDir } from "jsr:@std/http/file-server";

Deno.serve((req) => {
  const res = serveDir(req, { fsRoot: "build", quiet: true });
  return res.then((r) =>
    r.status === 404
      ? serveDir(new Request(new URL("/index.html", req.url)), { fsRoot: "build" })
      : r
  );
});
```

```bash
deployctl deploy --project=directstream-client serve.ts
```

Then set `CORS_ORIGINS` on the backend to the `*.deno.dev` domain
`deployctl` prints (or your custom domain, attached via the Deno Deploy
dashboard).

## Recommendation

Unless you already have infrastructure on Deno Deploy, skip this one — use
[`../vercel/`](../vercel/), [`../netlify/`](../netlify/), or
[`../cloudflare-pages/`](../cloudflare-pages/) for the client instead; all
three are zero-extra-code, dashboard-driven, and purpose-built for static
SPA hosting.
