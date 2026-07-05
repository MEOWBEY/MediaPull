# Deploy the client to your own server (VPS)

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
sudo cp /opt/directstream/deploy/client/vps/nginx-client.conf.example \
        /etc/nginx/sites-available/directstream-client
sudo sed -i 's/app.example.com/YOUR_CLIENT_DOMAIN/' /etc/nginx/sites-available/directstream-client
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

```bash
cd /opt/directstream/client
sudo -u directstream bash -c 'git pull && npm ci && npm run build'
# Option A: nothing else to do — the backend serves the new build immediately.
# Option B: nothing to restart either — nginx/Caddy serve files straight off disk.
```
