# DirectStream — client

The SvelteKit front-end for DirectStream: the UI, the in-browser HLS player, and
the proxy/stream API routes.

See the [root README](../README.md) for the full overview, architecture, and setup
for both the client and the FastAPI server.

## Quick start

```bash
npm install
cp .env.example .env        # set SERVER_BASE_URL / CLIENT_BASE_URL
npm run dev                 # http://localhost:5173
```

The client expects the FastAPI server (in `../server`) to be running. Client
environment variables are documented in the root README.

## Scripts

- `npm run dev` — start the dev server
- `npm run build` — production build
- `npm run preview` — preview the production build
- `npm run check` — type-check with svelte-check
- `npm run lint` / `npm run format` — lint and format
