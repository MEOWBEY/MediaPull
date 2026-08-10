# Deploy MediaPull on your own server (VPS)

Native install — no Docker — using **systemd** to keep the process alive and
**nginx** (or Caddy) in front for the domain + HTTPS. `install.sh` sets up the
backend **and**, if you want, the web client from the same box in one run.

Defaults: install path `/opt/mediapull`, system user `mediapull`, units
`mediapull.service` and `mediapull-pot.service`.

Any VPS works (DigitalOcean, Hetzner, Linode, a home server, …). For a
free-forever option, **Oracle Cloud's Always Free** tier is enough to run this.

## What's in this folder

```
deploy/
  install.sh          provision a fresh box (interactive, run once)
  update.sh           pull latest code + restart (run for every deploy after)
  uninstall.sh        stop/remove the service (--purge wipes everything)
  lib.sh              shared helpers, sourced by the three scripts above
  systemd/
    mediapull.service       backend unit (templated: port, user, resource caps)
    mediapull-pot.service   YouTube PO-token sidecar unit
  nginx/
    backend.conf.example  reverse proxy for the API
    client.conf.example   static server for the client (subdomain mode only)
  caddy/
    Caddyfile.example     Caddy alternative to nginx (hand-install)
```

The three scripts cover the whole lifecycle:

| Script | When | What it does |
|---|---|---|
| `install.sh` | once, fresh box | **interactive**: asks for domain, port, whether to serve the client here, and (private repo) a GitHub token, then sets up packages, service user, clone, venv, systemd unit, nginx + TLS, firewall (and the client build, if asked) |
| `update.sh` | every deploy after | pull code, reinstall deps, upgrade yt-dlp/gallery-dl, rebuild the client, restart, health-check — **no prompts** |
| `uninstall.sh` | to remove it | stop/remove service + nginx site(s); `--purge` also wipes repo/venv/user/cert |

## Glossary (skip if you know this)

- **VPS**: a small remote Linux computer you rent monthly, reached over SSH.
- **systemd service**: how Linux keeps a program running, restarts it on crash,
  and starts it on boot. `install.sh` configures this.
- **nginx / Caddy**: a *reverse proxy* in front of the app — handles your domain
  and HTTPS, forwards requests to the app on `127.0.0.1`.
- **DNS A record**: points your domain (e.g. `api.example.com`) at the VPS IP.
  Set it wherever you bought the domain, *before* running certbot.
- **certbot / TLS**: the free Let's Encrypt tool that gets you the HTTPS padlock.
  `install.sh` runs it once your domain resolves to the server.

## Quick install (recommended)

SSH into a fresh server, clone the repo, and run the installer from inside it:

```bash
ssh root@YOUR_SERVER_IP
apt update && apt install -y git
git clone https://github.com/meowbey/MediaPull.git /tmp/mediapull
sudo bash /tmp/mediapull/deploy/install.sh
```

(`/tmp/mediapull` is just a throwaway copy to launch the installer;
`install.sh` clones its own permanent copy into `/opt/mediapull` regardless.
Delete it afterwards with `rm -rf /tmp/mediapull`.)

> Running it as a **saved file** (not piped straight into `bash`) is what keeps
> it interactive. `curl … | bash` has no keyboard attached, so it silently uses
> defaults instead of asking the questions below.

### Without cloning

The installer sources shared helpers from `lib.sh`, so downloading
`install.sh` on its own fails with `lib.sh: No such file or directory`. Fetch
both into the same directory:

```bash
curl -fsSL https://raw.githubusercontent.com/meowbey/MediaPull/main/deploy/install.sh -o install.sh
curl -fsSL https://raw.githubusercontent.com/meowbey/MediaPull/main/deploy/lib.sh -o lib.sh
sudo bash install.sh
```

### What it asks

1. **API domain** (e.g. `api.example.com`) — blank skips HTTPS/nginx and runs
   on `127.0.0.1` only (fine for testing).
2. **Backend port** (default `8000`) — only matters if that port's taken.
3. **Public reverse-proxy port** (only if you gave a domain; default `80`) —
   the port *visitors* hit. If it's already in use, the installer detects it
   and asks for another rather than clobbering another service's config.
4. **How to serve the web client**: same domain (simplest), a separate
   subdomain on this box, or not here (hosting elsewhere / skipping).
5. **Install the YouTube PO-token provider?** (default yes) — see
   [YouTube PO tokens](#youtube-po-tokens). Also asks its port (default `4416`).
6. **Groq API key** for auto-subtitles — optional, free at
   [console.groq.com](https://console.groq.com); can be added later.

Answers are saved to `/opt/mediapull/.vps-deploy.env`, so `update.sh` /
`uninstall.sh` never re-ask.

### Non-interactive / scripted

Set the vars up front and nothing is asked:

```bash
sudo DOMAIN=api.example.com PORT=8000 CLIENT_MODE=same-domain bash install.sh
```

`CLIENT_MODE` ∈ `same-domain` | `subdomain` | `none` (add
`CLIENT_DOMAIN=app.example.com` with `subdomain`). `install.sh` is idempotent
— safe to re-run. Override the git remote with `REPO_URL=…`.

### Private repo

`install.sh` asks once for a GitHub token (a PAT with read access) and bakes it
into the checkout's remote, so `update.sh` and re-runs authenticate silently.
Non-interactive:

```bash
sudo GITHUB_TOKEN=ghp_xxx DOMAIN=api.example.com CLIENT_MODE=same-domain bash install.sh
```

A public repo needs none of this. Note the bootstrap `curl`/`git clone` above
is itself unauthenticated — for a private repo, clone that first step with a
token too (`git clone https://ghp_xxx@github.com/OWNER/REPO.git /tmp/mediapull`).

When it finishes, edit `/opt/mediapull/server/.env` for anything beyond what it
set, then `sudo systemctl restart mediapull`.

## Manual install, step by step

What `install.sh` automates — read this to customize or if the script doesn't
fit your distro.

### 1. System packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg nginx git curl
```

(3.10+ is fine — nothing needs a specific minor version.)

### 2. Service user + clone

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin mediapull
sudo -u mediapull git clone https://github.com/meowbey/MediaPull.git /opt/mediapull
```

### 3. Python environment

```bash
cd /opt/mediapull/server
sudo -u mediapull python3 -m venv venv
sudo -u mediapull ./venv/bin/pip install -r requirements.txt
sudo -u mediapull cp .env.production.example .env
sudo -u mediapull nano .env
```

For a production box, in `.env`:
- `CORS_ORIGINS=https://your-client-domain.example` — pin it, don't leave `*`.
  (With `*`, the app disables credentialed CORS, because browsers reject
  `Access-Control-Allow-Origin: *` together with credentials.)
- `COOKIE_FILE_PATHS=/opt/mediapull/server/cookies.txt` if using server-side cookies
  (`chmod 600`, owned by `mediapull`).
- `ADMIN_TOKEN=…` to enable refreshing those cookies over HTTP without SSH — see
  [Server-wide cookies](#server-wide-cookies). Empty = disabled.
- `ADMIN_USERNAME` + `ADMIN_PASSWORD_HASH` to enable the admin panel — see
  [Admin panel](#admin-panel). Empty = disabled.
- `PROXY_ALLOWED_HOSTS=googlevideo.com,cdninstagram.com,fbcdn.net,…` if you
  expose the box publicly — see [Security](#security).
- Leave `PORT` alone here; the bound port comes from the systemd unit (step 4).

### 4. systemd service

The unit uses `__…__` placeholders; fill them in (skip `sed` values you want at
their default):

```bash
sed 's#__REPO_DIR__#/opt/mediapull#g; s/__SERVICE_USER__/mediapull/g; s/__PORT__/8000/; s/__MEMORY_MAX__/1024M/; s/__CPU_QUOTA__/100%/' \
  /opt/mediapull/deploy/systemd/mediapull.service \
  | sudo tee /etc/systemd/system/mediapull.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now mediapull
sudo systemctl status mediapull
journalctl -u mediapull -f
```

### 5. Reverse proxy + domain + TLS

Point your domain's A/AAAA record at the server IP first, then:

**nginx:**
```bash
sed 's/api.example.com/YOUR_DOMAIN/; s/__PORT__/8000/; s/__PUBLIC_PORT__/80/' \
  /opt/mediapull/deploy/nginx/backend.conf.example \
  | sudo tee /etc/nginx/sites-available/mediapull-api > /dev/null
sudo ln -s /etc/nginx/sites-available/mediapull-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN
```

**Caddy (automatic HTTPS, no certbot):**
```bash
sed 's/api.example.com/YOUR_DOMAIN/; s/__PORT__/8000/' \
  /opt/mediapull/deploy/caddy/Caddyfile.example \
  | sudo tee /etc/caddy/Caddyfile > /dev/null
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

`ffmpegAvailable` / `galleryDlAvailable` should both be `true` — if not, see
[Troubleshooting](#troubleshooting). `potAvailable` shows whether the PO-token
provider answered (see [YouTube PO tokens](#youtube-po-tokens)); `false` means
YouTube age-gated / bot-checked videos will likely fail. `splitAudioEnabled`
reflects the split-audio feature (ffmpeg + `SPLIT_AUDIO_ENABLED`).

## YouTube PO tokens

YouTube increasingly blocks extraction from datacenter/cloud IPs (what a VPS
is) with *"Sign in to confirm you're not a bot"*, or refuses age-restricted
videos even with cookies. The fix is a **PO token** — a per-video
proof-of-not-a-bot token yt-dlp attaches to the request.

Hand-copying a token from a browser **no longer works** (YouTube binds tokens
to the video ID). The supported fix is the companion service
[`bgutil-ytdlp-pot-provider`](https://github.com/Brainicism/bgutil-ytdlp-pot-provider),
which fetches a fresh token per extraction.

`install.sh` sets this up (default yes): a pip plugin yt-dlp auto-detects, plus
a small Node server running as its own systemd service (`mediapull-pot`) on
`127.0.0.1:4416`. If you chose a different port, it sets
`YOUTUBE_POT_BASE_URL=http://127.0.0.1:<port>` in `.env` accordingly. Check it:

```bash
sudo systemctl status mediapull-pot
journalctl -u mediapull-pot -n 50
```

`update.sh` keeps the plugin and server version-matched (they speak a
version-checked protocol — letting them drift breaks the plugin).

## Server-wide cookies

Most of X/Twitter and private/login-only Instagram refuse to serve content
**at all** without a session — no PO token fixes that. `install.sh` sets up
`server/cookies.txt` (from `server/cookies.example.txt`) and points
`COOKIE_FILE_PATHS` at it:

```bash
sudo nano /opt/mediapull/server/cookies.txt
```

Paste Netscape-format `cookies.txt` — export with
["Get cookies.txt LOCALLY"](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc),
ideally from a **throwaway account**. Save, then `sudo systemctl restart
mediapull`. This file is never touched by `update.sh`/`uninstall.sh`.

### Refreshing cookies without SSH (optional)

Exported cookies go stale (the account's session rotates), and each refresh
otherwise means an SSH session. To update them over HTTP instead, set a secret
in `.env` and restart once:

```bash
ADMIN_TOKEN=$(openssl rand -hex 32)   # put this line's value in server/.env
```

Then push a fresh export any time — no restart, it takes effect on the next
extraction:

```bash
read -rs TOKEN            # paste the ADMIN_TOKEN value (keeps it out of history)
curl -X POST https://YOUR_DOMAIN/admin/cookies \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data "$(jq -Rs '{cookies:.}' < fresh-cookies.txt)"
```

It writes the first path in `COOKIE_FILE_PATHS`. Leave `ADMIN_TOKEN` empty to
disable the endpoint (it returns 404). **Only call it over HTTPS** — the token
is a bearer secret. Rotate it by changing `.env` and restarting.

## Admin panel

Served at `https://YOUR_DOMAIN/admin` — a small ops console with live logs &
SSE tail, job list/cancel, banned-IP & blocked-domain rules, a safe `.env`
editor (validates, keeps a `.bak` before writing), and a server-cookie editor,
plus the `POST /admin/cookies` upload flow from above without needing the
token.

`install.sh` sets this up if you answer its username/password prompt (it hashes
the password with the app's own PBKDF2 before writing `.env`); it also installs
a polkit rule letting the `mediapull` user restart its own unit, which powers
the panel's "Restart service" button (systemd installs only — Docker/small
hosts without polkit just get "restart manually").

Manual setup instead:

```bash
cd /opt/mediapull/server
sudo -u mediapull venv/bin/python - <<'PY'
from app.admin import hash_password
print(hash_password('choose-a-strong-password'))
PY
# add the printed value to server/.env:
#   ADMIN_USERNAME=yourname
#   ADMIN_PASSWORD_HASH=pbkdf2_sha256$...
# then:
sudo sed 's/__SERVICE_USER__/mediapull/g' \
  /opt/mediapull/deploy/polkit/mediapull.rules \
  > /etc/polkit-1/rules.d/50-mediapull.rules
sudo systemctl restart mediapull
```

Admin credentials are never stored plaintext: only the PBKDF2 hash lands in
`.env` (update.sh never touches it — your password survives every update).
Change a password later from the panel's Settings files tab, or by editing
`ADMIN_PASSWORD_HASH` in `server/.env` and restarting. Left blank at install,
the panel stays disabled until both keys are set.

## Resource limits

`install.sh` detects CPU cores + RAM and caps the service (`MemoryMax=` /
`CPUQuota=` — roughly 70% of RAM, all-but-one core), leaving headroom for nginx
and anything else on the box. On a small box (≤2 vCPU or ≤2GB RAM) it also sets
`TRANSCRIBE_MAX_CONCURRENT_JOBS=1` and `TRANSCRIBE_WORKERS=1` (those run the
CPU-heavy ffmpeg work).

These caps are re-applied on every `update.sh` (it re-templates the unit from
`.vps-deploy.env`), so editing the installed
`/etc/systemd/system/mediapull.service` is overwritten next update. For a
permanent override use `systemctl edit mediapull` (a drop-in), then
`systemctl daemon-reload && systemctl restart mediapull`.

## Updating later

```bash
sudo /opt/mediapull/deploy/update.sh
```

Pulls, reinstalls deps, upgrades yt-dlp/gallery-dl, rebuilds the client (if
installed), restarts, and checks `/health` — reusing the saved GitHub
credential, so even a private repo never re-prompts.

**Rollback** if an update breaks something (systemd only cares that the files on
disk are valid, not which commit):

```bash
cd /opt/mediapull
sudo -u mediapull git log --oneline -5
sudo -u mediapull git checkout <good-commit-hash>
sudo -u mediapull server/venv/bin/pip install -r server/requirements.txt
sudo systemctl restart mediapull
```

Return to the tip with `git checkout <branch>` afterward (running `update.sh`
on a detached HEAD refuses and tells you this). Tail logs with
`journalctl -u mediapull -f`.

## Removing it later

```bash
sudo /opt/mediapull/deploy/uninstall.sh            # stop + remove service/nginx, keep data
sudo /opt/mediapull/deploy/uninstall.sh --purge    # + wipe repo, venv, user, TLS cert(s)
```

`uninstall.sh` reads your saved domain/client answers automatically. `--purge`
asks for an explicit `YES` before deleting the repo and the service user.

After removal, nginx is still installed and will show its default
**"Welcome to nginx!"** page on port 80. This is harmless but visible.
If nothing else on the box uses nginx, remove it:

```bash
sudo systemctl stop nginx && sudo systemctl disable nginx
sudo apt remove --purge nginx nginx-common && sudo apt autoremove
```

Skip this if another service on the box uses nginx.

## Security

`GET /proxy-video` fetches user-supplied URLs. The proxy blocks internal
targets (loopback, RFC-1918, link-local, IPv4-mapped IPv6) and re-checks the
host on every redirect hop and against resolved DNS, so basic SSRF is covered.
Still, for a public box you should also:

- Set `PROXY_ALLOWED_HOSTS` to the media CDNs you actually use, so the proxy
  won't fetch arbitrary hosts, **or** set `PROXY_ENABLED=false` to disable it.
- Put auth / a firewall / a VPN in front if it isn't meant to be public.

Auth cookies are never placed in proxy URLs (the client exchanges them for an
opaque short-lived token via `POST /proxy-token`), so copied/QR/shared links
don't leak sessions.

## Troubleshooting

- **`ffmpegAvailable: false` on `/health`**: ffmpeg is used by auto-subtitles
  and split-audio, so this can go unnoticed until someone uses either.
  `install.sh` installs ffmpeg via apt; if you skipped/moved it, set
  `FFMPEG_PATH`/`FFPROBE_PATH` in `.env` to the absolute path and restart.
- **"This site or URL isn't supported" on a link that used to work**: the
  pinned `yt-dlp`/`gallery-dl` is behind. `update.sh` always upgrades both to
  latest — run it even without new app code.
- **Site stays on HTTP — no HTTPS after install**: certbot couldn't complete
  the Let's Encrypt challenge, so the install fell back to plain HTTP. The
  challenge reaches this box on **port 80** and the cert then serves on **443**;
  both must be open to the public internet. Check, in order:
  1. **DNS** actually points here: `dig +short YOUR_DOMAIN` must return this
     server's public IP (not a Cloudflare/proxy IP — if you use Cloudflare, set
     that record to "DNS only" / grey-cloud until the cert is issued).
  2. **Cloud/provider firewall**: AWS security groups, GCP/Oracle/Hetzner
     firewalls, etc. block 80/443 by default and `install.sh` can't touch them.
     Open both there, separately from ufw.
  3. Then re-run just the cert step (no need to re-run the whole installer):
     ```bash
     sudo certbot --nginx -d YOUR_DOMAIN --redirect
     ```
  The installer now opens 80/443 in `ufw` before running certbot, so an active
  local firewall is no longer the cause — it's almost always DNS or a provider
  firewall above.
