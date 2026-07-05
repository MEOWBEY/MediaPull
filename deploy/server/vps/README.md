# Deploy the backend to your own server (VPS)

Native install — no Docker — using systemd to keep the process alive and
nginx (or Caddy) in front for the domain + TLS. If you'd rather run it as a
container instead, see [`../docker/`](../docker/)'s `docker-compose.yml`,
which does the equivalent with Caddy baked in.

This covers the **backend only**. If you also want to serve the client from
this same box, see [`../../client/vps/`](../../client/vps/) once you're done
here — it adds one more nginx/Caddy server block, no conflict with this one.

Any VPS works (DigitalOcean, Hetzner, Linode, a home server, …). For an
actually-free-forever option, **Oracle Cloud's Always Free** tier includes a
small compute instance that's enough to run this.

Three scripts here cover the service's whole lifecycle — provision once,
update routinely, remove if you ever need to:

| Script | When | What it does |
|---|---|---|
| `install.sh` | once, on a fresh box | packages, service user, clone, venv, systemd unit, nginx + TLS, firewall |
| `update.sh` | every deploy after that | pull latest code, reinstall deps, restart, health-check |
| `uninstall.sh` | if you want it gone | stop/remove the service + nginx site (add `--purge` to also wipe the repo/venv/user/cert) |

## Quick install (scripted)

```bash
scp -r deploy root@YOUR_SERVER_IP:/tmp/directstream-deploy   # or git clone the repo there directly
ssh root@YOUR_SERVER_IP
sudo DOMAIN=api.example.com /tmp/directstream-deploy/server/vps/install.sh
```

`install.sh` is idempotent (safe to re-run) and, if `/opt/directstream`
doesn't already exist, clones the repo itself
(`REPO_URL=... install.sh` to override which git remote/fork it pulls).
Omit `DOMAIN` to skip nginx/TLS and just get the service listening on
`127.0.0.1:8000` — add a reverse proxy yourself later.

When it finishes, edit `/opt/directstream/server/.env` for anything beyond
`CORS_ORIGINS` (cookies, proxy, YouTube player clients, …) and
`sudo systemctl restart directstream`.

**From here on, use `update.sh` for every subsequent deploy** — see
**Updating later** below. The manual steps below are what `install.sh`
automates; read them if you want to understand or customize what it's
doing, or if you're on a distro where the script doesn't quite fit.

## Manual install, step by step

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv ffmpeg nginx git
# or, for Caddy instead of nginx:
#   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
#   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
#   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
#   sudo apt update && sudo apt install -y caddy
```

### 2. Create a dedicated user and clone the repo

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin directstream
sudo -u directstream git clone https://github.com/<you>/Direct-Linker.git /opt/directstream
```

(Adjust the repo URL. If deploying from a private repo or local copy,
`scp`/`rsync` the tree to `/opt/directstream` instead and `chown -R
directstream:directstream /opt/directstream`.)

### 3. Set up the Python environment

```bash
cd /opt/directstream/server
sudo -u directstream python3.12 -m venv venv
sudo -u directstream ./venv/bin/pip install -r requirements.txt
sudo -u directstream cp .env.production.example .env
sudo -u directstream nano .env   # set CORS_ORIGINS to your client's origin, etc.
```

Notably in `.env` for a production box:
- `CORS_ORIGINS=https://your-client-domain.example` (not `*`, once you know it)
- `COOKIE_FILE=/opt/directstream/server/cookies.txt` if you're using a
  server-side default cookie file (upload it there, `chmod 600`, owned by
  `directstream`)
- Leave `HOST`/`PORT` alone — the systemd unit binds gunicorn to
  `127.0.0.1:8000` directly; nginx/Caddy is what's actually public-facing.

### 4. Install and start the systemd service

```bash
sudo cp /opt/directstream/deploy/server/vps/directstream.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now directstream
sudo systemctl status directstream       # should show "active (running)"
journalctl -u directstream -f            # tail logs
```

### 5. Reverse proxy + domain + TLS

Point your domain's A/AAAA record at the server's IP first, then:

**nginx:**
```bash
sudo cp /opt/directstream/deploy/server/vps/nginx-backend.conf.example \
        /etc/nginx/sites-available/directstream-api
sudo sed -i 's/api.example.com/YOUR_DOMAIN/' /etc/nginx/sites-available/directstream-api
sudo ln -s /etc/nginx/sites-available/directstream-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN   # obtains + auto-configures the TLS cert, sets up renewal
```

**Caddy (simpler — automatic HTTPS, no certbot step):**
```bash
sudo cp /opt/directstream/deploy/server/vps/Caddyfile.example /etc/caddy/Caddyfile
sudo sed -i 's/api.example.com/YOUR_DOMAIN/' /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

### 6. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'   # or: sudo ufw allow 80,443/tcp   (Caddy)
sudo ufw enable
```

### 7. Verify

```bash
curl https://YOUR_DOMAIN/health
```

## Updating later

Use the bundled script — it pulls, reinstalls dependencies, restarts, and
verifies `/health` in one go:

```bash
sudo /opt/directstream/deploy/server/vps/update.sh
```

Or do it by hand:

```bash
cd /opt/directstream
sudo -u directstream git pull --ff-only
sudo -u directstream server/venv/bin/pip install -r server/requirements.txt
sudo systemctl restart directstream
curl -fsS http://127.0.0.1:8000/health   # confirm it came back up
```

**If an update breaks something**, roll back to the last known-good commit
and restart — systemd doesn't care which commit is checked out, only that
the files on disk are valid:

```bash
cd /opt/directstream
sudo -u directstream git log --oneline -5      # find the last-good commit hash
sudo -u directstream git checkout <good-commit-hash>
sudo -u directstream server/venv/bin/pip install -r server/requirements.txt
sudo systemctl restart directstream
```

Then `git checkout <branch-name>` to return to the tip once you've sorted
out the issue upstream. Watch logs live during any update with
`journalctl -u directstream -f`.

## Removing it later

```bash
sudo /opt/directstream/deploy/server/vps/uninstall.sh            # stop + remove service/nginx, keep data
sudo DOMAIN=api.example.com /opt/directstream/deploy/server/vps/uninstall.sh --purge   # + wipe repo, venv, user, TLS cert
```

`--purge` asks for an explicit `YES` confirmation before deleting the repo
directory and before removing the service user — it won't silently destroy
anything.

## Notes

- The security note in the root [`README.md`](../../../README.md) applies
  here too: `GET /proxy-video` fetches arbitrary user-supplied URLs with no
  host allow-list. On a public box, either restrict who can reach the
  service (firewall/VPN/auth in front) or add an allow-list before exposing
  it broadly.
- Want the client served from this same box instead of Vercel/Netlify/
  Cloudflare Pages? Continue to [`../../client/vps/`](../../client/vps/).
