# Deploy the backend to Fly.io

> **Fly.io no longer has an ongoing free tier** (removed for new accounts in
> October 2024) — new orgs get a short trial (a few VM-hours or ~7 days),
> then it's pay-as-you-go (roughly $2–5/mo for one small always-on
> instance). If you had a legacy Hobby/Launch/Scale account from before the
> cutoff, you're grandfathered onto the old free allowance. For a
> genuinely-free always-on container host today, see
> [`../northflank/`](../northflank/) instead — everything below still
> applies if you're on Fly by choice or already have credits/a legacy plan.

Fly always builds and runs a container image — there's no meaningfully
different "native/no-Docker" path here the way Railway's Nixpacks offers
(Fly's own buildpack auto-detection would just generate a Dockerfile behind
the scenes anyway, and that generated one wouldn't know to install
`ffmpeg`). So this uses `deploy/server/docker/Dockerfile` directly, which is
the single-process image — API + built client together, one service, no
CORS to configure. If you'd rather split the client onto Vercel/Netlify/
Cloudflare Pages, see **Split-deploy** below.

## Install

```bash
# https://fly.io/docs/flyctl/install/
curl -L https://fly.io/install.sh | sh   # or: brew install flyctl
fly auth signup    # or: fly auth login
```

## Setup

Run everything from the **repo root** (the Dockerfile build needs both
`client/` and `server/` in its context):

```bash
fly launch --config deploy/server/flyio/fly.toml \
            --dockerfile deploy/server/docker/Dockerfile \
            --no-deploy
# review the generated app name / region in the prompts, then:
fly deploy  --config deploy/server/flyio/fly.toml \
            --dockerfile deploy/server/docker/Dockerfile
```

Set secrets (Fly's equivalent of env vars) instead of committing them:

```bash
fly secrets set CORS_ORIGINS=https://your-domain.example ENABLE_IMPERSONATION=true
```

Attach a custom domain:

```bash
fly certs create your-domain.example   # Fly provisions the TLS cert automatically
```

Point your domain's DNS at the address `fly certs show your-domain.example`
prints (an A/AAAA record, or a CNAME to `<app-name>.fly.dev`).

## Split-deploy (client elsewhere)

Build the image with the client pointed at this Fly app instead of baking
it in same-origin:

```bash
fly deploy --config deploy/server/flyio/fly.toml \
           --dockerfile deploy/server/docker/Dockerfile \
           --build-arg VITE_API_BASE_URL=https://your-app.fly.dev
```

Then deploy the client separately (see [`../../client/`](../../client/)) and
set `CORS_ORIGINS` on this Fly app to the client's domain.

## Notes

- `min_machines_running = 0` in `fly.toml` lets the app scale to zero when
  idle (cheapest, small cold-start on the next request) — set it to `1` if
  you want it always warm and don't mind the extra usage.
- Fly requires a card on file even for the trial. See the banner at the top
  of this file — [`../northflank/`](../northflank/) is the more realistic
  free option as of 2026.
