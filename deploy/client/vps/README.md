# Deploy the client to your own server (VPS)

**Most people don't need anything in this folder.** Running
[`../../server/vps/install.sh`](../../server/vps/install.sh) already asks
you whether to serve the client from the same box (same domain or a
subdomain) and sets all of this up automatically. Come here only if:

- you're hosting the client somewhere *other* than the server VPS
  (a separate box, or a service like Vercel/Netlify/Cloudflare Pages using
  the split-deploy configs under [`../vercel/`](../vercel/) etc.), or
- you want to understand/customize exactly what the installer's client step
  does, or set it up by hand on a distro the script doesn't fit.

Two ways to serve the client from your own box, once the backend is running
per [`../../server/vps/`](../../server/vps/).

## Option A — combined single process (simplest, skip all of this)

Don't run a separate client at all: point the backend at the built client
with `CLIENT_DIR`, and it serves both from one process/one port (no
separate nginx block, no CORS to configure).

```bash
cd /opt/directstream/client
sudo -u directstream bash -c 'npm ci && npm run build'
```

Then in `server/.env` (or the systemd unit's `EnvironmentFile`):
```
CLIENT_DIR=/opt/directstream/client/build
```

```bash
sudo systemctl restart directstream
```

Now the backend's own domain (from
[`../../server/vps/`](../../server/vps/)) serves the whole app.

## Option B — separate static site (own subdomain, e.g. app.example.com)

Useful if you want the client on its own domain/subdomain, cached and
served independently of the API.

```bash
cd /opt/directstream/client
sudo -u directstream bash -c 'VITE_API_BASE_URL=https://api.example.com npm ci && npm run build'
```

```bash
sed 's/app.example.com/YOUR_CLIENT_DOMAIN/' \
  /opt/directstream/deploy/client/vps/nginx-client.conf.example \
  | sudo tee /etc/nginx/sites-available/directstream-client > /dev/null
sudo ln -s /etc/nginx/sites-available/directstream-client /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx -d YOUR_CLIENT_DOMAIN
```

Then, on the backend, set `CORS_ORIGINS=https://YOUR_CLIENT_DOMAIN` in
`server/.env` and `sudo systemctl restart directstream`.

Using Caddy instead of nginx? Add a second site block to the same
`/etc/caddy/Caddyfile` used for the backend:

```caddyfile
app.example.com {
	root * /opt/directstream/client/build
	try_files {path} /index.html
	file_server
	encode gzip
}
```

## Updating later

If you set the client up via [`../../server/vps/install.sh`](../../server/vps/install.sh),
just use [`../../server/vps/update.sh`](../../server/vps/update.sh) — it
rebuilds the client too. Doing it by hand:

```bash
cd /opt/directstream/client
sudo -u directstream bash -c 'git pull && npm ci && npm run build'
# Option A: nothing else to do — the backend serves the new build immediately.
# Option B: nothing to restart either — nginx/Caddy serve files straight off disk.
```

