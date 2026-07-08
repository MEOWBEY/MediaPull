# Deploy the backend (and optionally the client) to your own server (VPS)

Native install — no Docker — using systemd to keep the process alive and
nginx (or Caddy) in front for the domain + TLS. If you'd rather run it as a
container instead, see [`../docker/`](../docker/)'s `docker-compose.yml`,
which does the equivalent with Caddy baked in.

**`install.sh` handles the backend AND the client in one run** — it asks a
few questions (domain, port, whether to serve the web client from this same
box) and sets up whichever pieces you asked for. You don't need to run
anything separately in [`../../client/vps/`](../../client/vps/) unless you
want the client on a totally different host (Vercel/Netlify/Cloudflare
Pages/etc.) — that folder is documentation for that alternate path only.

Any VPS works (DigitalOcean, Hetzner, Linode, a home server, …). For an
actually-free-forever option, **Oracle Cloud's Always Free** tier includes a
small compute instance that's enough to run this.

Three scripts here cover the whole lifecycle — provision once, update
routinely, remove if you ever need to:

| Script | When | What it does |
|---|---|---|
| `install.sh` | once, on a fresh box | **interactive**: asks for a domain, a port, and whether to serve the client here too, then sets up packages, service user, clone, venv, systemd unit, nginx + TLS, firewall (and the client build, if you asked for it) |
| `update.sh` | every deploy after that | pull latest code, reinstall deps, rebuild the client (if one was installed), restart, health-check |
| `uninstall.sh` | if you want it gone | stop/remove the service + nginx site(s) (add `--purge` to also wipe the repo/venv/user/cert) |

## What is a "VPS", and what do these words mean?

- **VPS (Virtual Private Server)**: a small remote computer you rent by the
  month, that you fully control (unlike shared hosting). You'll get an IP
  address and a way to log in over SSH (a secure remote terminal).
- **systemd service**: the standard way Linux keeps a program running in the
  background, restarts it if it crashes, and starts it automatically when
  the server reboots. `install.sh` sets this up for you.
- **nginx / Caddy**: a "reverse proxy" — a small program that sits in front
  of your app, handles the public internet-facing side (your domain name,
  HTTPS), and forwards real requests to the app running privately on the
  same machine.
- **DNS / domain / A record**: your domain name (e.g. `example.com`) needs a
  "DNS A record" pointing at your VPS's IP address before HTTPS/certbot can
  work — this is configured wherever you bought the domain (Namecheap,
  Cloudflare, Google Domains, etc.), not on the server itself.
- **certbot / TLS certificate**: the free tool (from Let's Encrypt) that gets
  your site the padlock/HTTPS. `install.sh` runs this for you automatically
  once your domain points at the server.

## Quick install (scripted, interactive)

SSH into your fresh server, then download and run just the one installer
script (it clones the full project itself once it starts — you don't need
a copy of the repo on the server ahead of time):

```bash
ssh root@YOUR_SERVER_IP
curl -fsSL https://raw.githubusercontent.com/MEOWBEY/direct-stream/main/deploy/server/vps/install.sh -o install.sh
sudo bash install.sh
```

(`ssh root@YOUR_SERVER_IP` logs into your server as an administrator —
replace `YOUR_SERVER_IP` with the address your VPS provider gave you.
`curl -o install.sh` downloads that one script to your current directory —
running it as a saved file, not piped straight into `bash`, is what keeps it
interactive; see the note below.)

If you'd rather review the code before running anything, or you're
deploying a fork, clone the whole repo first and run the script from inside
it instead:

```bash
ssh root@YOUR_SERVER_IP
git clone https://github.com/MEOWBEY/direct-stream.git /tmp/direct-stream
sudo  bash /tmp/direct-stream/deploy/server/vps/install.sh
```

(`/tmp` is Linux's throwaway-files folder — anything there is fine to
delete or gets cleared automatically on reboot. This clone is just a
temporary copy to get the installer running; `install.sh` clones its own
permanent copy into `/opt/directstream` regardless of which method you use
to fetch it.)

It will ask you, in plain language:
1. **What domain will the API use?** (e.g. `api.example.com`) — leave blank
   to skip HTTPS entirely and just get it running on `127.0.0.1` (fine for
   testing, not for real use).
2. **What port should the backend listen on?** (default `8000` — only
   matters if you're already using that port for something else, or want to
   run two copies on one box).
3. **What public port should the reverse proxy use?** (only asked if you gave
   a domain; default `80`). This is the port *visitors* hit, separate from
   the backend's own internal port above. If something else on the box is
   already listening on the port you pick `install.sh` detects it up front
   and asks you to pick a different one instead of silently overwriting that
   other service's nginx config (which is what used to happen, and is why a
   previous version of this installer could take an unrelated panel
   offline). Point your browser at `http://your-domain:PORT` (or just the
   domain if you kept the default 80).
4. **How do you want to serve the web client?**
   - *Same domain as the API* (simplest — recommended for most people)
   - *A separate subdomain on this same server* (e.g. `app.example.com`)
   - *Don't serve it here* (you're hosting it on Vercel/Netlify/elsewhere, or
     skipping the client for now)
5. **Install the PO token provider for YouTube?** (default: yes) — see
   [YouTube PO tokens](#youtube-po-tokens) below for what this is and why
   you almost always want it. Right after, you'll also get an optional
   prompt for a **static PO token** — leave it blank unless you specifically
   have one; the automatic provider you just installed handles this for you.
6. **Groq API key for auto-subtitles?** — optional, leave blank to skip.
   Get a free one (no card required) at
   [console.groq.com](https://console.groq.com); paste it here or add it to
   `server/.env` later.

Answer once — `install.sh` remembers your answers (in
`/opt/directstream/.vps-deploy.env`) so `update.sh`/`uninstall.sh` don't ask
again later.

**Piping the script through `curl | bash` skips the questions** (there's no
keyboard attached to answer them) and silently falls back to defaults —
download/clone the script first and run it directly (as shown above) if you
want the interactive prompts.

If you already know all the answers and want a fully non-interactive run
(e.g. scripting a second identical box), set the equivalent environment
variables and nothing will be asked:

```bash
sudo DOMAIN=api.example.com PORT=8000 CLIENT_MODE=same-domain bash install.sh
```

(`CLIENT_MODE` is one of `same-domain`, `subdomain`, or `none`; add
`CLIENT_DOMAIN=app.example.com` alongside `subdomain`.)

`install.sh` is idempotent (safe to re-run) and, if `/opt/directstream`
doesn't already exist, clones the repo itself
(`REPO_URL=... install.sh` to override which git remote/fork it pulls).

When it finishes, edit `/opt/directstream/server/.env` for anything beyond
what it already set (cookies, proxy, YouTube player clients, Groq API key
for auto-subtitles, …) and `sudo systemctl restart directstream`.

**From here on, use `update.sh` for every subsequent deploy** — see
**Updating later** below. The manual steps below are what `install.sh`
automates; read them if you want to understand or customize what it's
doing, or if you're on a distro where the script doesn't quite fit.

## Manual install, step by step

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg nginx git
# or, for Caddy instead of nginx:
#   sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
#   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
#   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
#   sudo apt update && sudo apt install -y caddy
```

(Nothing in this app needs a specific Python minor version — 3.10+ is fine.
`python3`/`python3-venv` picks whatever your distro already ships by
default, no PPA needed. `install.sh` does the same detection automatically.)

### 2. Create a dedicated user and clone the repo

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin directstream
sudo -u directstream git clone https://github.com/MEOWBEY/direct-stream.git /opt/directstream
```

(Adjust the repo URL. If deploying from a private repo or local copy,
`scp`/`rsync` the tree to `/opt/directstream` instead and `chown -R
directstream:directstream /opt/directstream`.)

### 3. Set up the Python environment

```bash
cd /opt/directstream/server
sudo -u directstream python3 -m venv venv
sudo -u directstream ./venv/bin/pip install -r requirements.txt
sudo -u directstream cp .env.production.example .env
sudo -u directstream nano .env   # set CORS_ORIGINS to your client's origin, etc.
```

Notably in `.env` for a production box:
- `CORS_ORIGINS=https://your-client-domain.example` (not `*`, once you know it)
- `COOKIE_FILE=/opt/directstream/server/cookies.txt` if you're using a
  server-side default cookie file (upload it there, `chmod 600`, owned by
  `directstream`)
- Leave `HOST`/`PORT` alone here — the port gunicorn actually binds to comes
  from `directstream.service` below, not this file (see step 4 if you want a
  port other than 8000).

### 4. Install and start the systemd service

The unit file uses `__PORT__` as a placeholder so you can pick a port other
than the default 8000 (skip the `sed` if 8000 is fine):

```bash
sed 's/__PORT__/8000/' /opt/directstream/deploy/server/vps/directstream.service \
  | sudo tee /etc/systemd/system/directstream.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now directstream
sudo systemctl status directstream       # should show "active (running)"
journalctl -u directstream -f            # tail logs
```

### 5. Reverse proxy + domain + TLS

Point your domain's A/AAAA record at the server's IP first, then:

**nginx:**
```bash
sed 's/api.example.com/YOUR_DOMAIN/; s/__PORT__/8000/' \
  /opt/directstream/deploy/server/vps/nginx-backend.conf.example \
  | sudo tee /etc/nginx/sites-available/directstream-api > /dev/null
sudo ln -s /etc/nginx/sites-available/directstream-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d YOUR_DOMAIN   # obtains + auto-configures the TLS cert, sets up renewal
```

**Caddy (simpler — automatic HTTPS, no certbot step):**
```bash
sed 's/api.example.com/YOUR_DOMAIN/; s/__PORT__/8000/' \
  /opt/directstream/deploy/server/vps/Caddyfile.example \
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

`ffmpegAvailable`/`galleryDlAvailable` in that response should both be
`true` — if either is `false`, see the **Known issues** note below.

## YouTube PO tokens

YouTube increasingly blocks extraction from datacenter/cloud IPs (exactly
what a VPS is) with errors like *"Sign in to confirm you're not a bot"*, or
refuses age-restricted videos even with cookies added. The fix is a **PO
token** — a per-video proof-of-not-a-bot token yt-dlp needs to attach to the
request.

Manually copying a PO token out of a browser used to work but **no longer
does** — YouTube now binds tokens to the specific video ID, so a hand-copied
token is already stale by the time you'd paste it in. The supported fix is a
small companion service, [`bgutil-ytdlp-pot-provider`](https://github.com/Brainicism/bgutil-ytdlp-pot-provider),
that fetches a fresh token automatically for every extraction.

`install.sh` offers to set this up for you (question 4, defaults to yes):
it installs a pip plugin that yt-dlp auto-detects, plus a small Node.js
server running as its own systemd service (`directstream-pot`, listening on
`127.0.0.1:4416` — nothing further to configure). If you skipped it, or want
to check it's running:

```bash
sudo systemctl status directstream-pot
journalctl -u directstream-pot -n 50
```

`update.sh` keeps the plugin and the server version-matched automatically on
every update — they speak a version-checked protocol to each other, so
letting them drift apart will cause the plugin to stop working.

## Server-wide cookies

Beyond YouTube, most of X/Twitter and any private/login-only Instagram post
refuse to serve content **at all** without a logged-in session — no PO token
fixes that, you need real cookies. `install.sh` sets up
`server/cookies.txt` (from the tracked `server/cookies.example.txt`
template) and points `COOKIE_FILE` at it automatically:

```bash
sudo nano /opt/directstream/server/cookies.txt
```

Paste Netscape-format `cookies.txt` content — export it with the
["Get cookies.txt LOCALLY"](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
browser extension, ideally from a **throwaway logged-in account**, not your
main one. Save, then `sudo systemctl restart directstream`. This file is
never touched by `update.sh`/`uninstall.sh`, so it survives every future
update.

## Resource limits

`install.sh` detects the box's CPU core count and total RAM and caps the
backend service accordingly (`MemoryMax=`/`CPUQuota=` in the systemd unit) —
roughly 70% of RAM and all-but-one CPU core, leaving headroom for nginx and
anything else sharing the VPS (another panel, a database, …). On a small box
(≤2 vCPU or ≤2GB RAM) it also dials back `TRANSCRIBE_MAX_CONCURRENT_JOBS` and
`TRANSCRIBE_WORKERS` to `1` each in `server/.env`, since those two are what
actually run ffmpeg (CPU-heavy) — this is the knob that matters if you see
the box pegged near 100% CPU while auto-subtitle jobs are running.

These caps are re-applied on every `update.sh` run (it re-templates the unit
from the values saved in `.vps-deploy.env`, not just restarts), so a manual
edit to the installed `/etc/systemd/system/directstream.service` file will be
overwritten on the next update. For a permanent override, use
`systemctl edit directstream` instead (it layers a drop-in on top rather than
editing the generated file), then `systemctl daemon-reload && systemctl
restart directstream`.

## Updating later

Use the bundled script — it pulls, reinstalls dependencies, rebuilds the
client (if `install.sh` set one up), restarts, and verifies `/health` in one
go:

```bash
sudo /opt/directstream/deploy/server/vps/update.sh
```

Or do it by hand:

```bash
cd /opt/directstream
sudo -u directstream git pull --ff-only
sudo -u directstream server/venv/bin/pip install -r server/requirements.txt
sudo systemctl restart directstream
curl -fsS http://127.0.0.1:8000/health   # confirm it came back up (adjust the port if you chose a different one)
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
out the issue upstream (running `update.sh` again on a detached-HEAD
checkout will refuse and tell you to do this first). Watch logs live during
any update with `journalctl -u directstream -f`.

## Removing it later

```bash
sudo /opt/directstream/deploy/server/vps/uninstall.sh            # stop + remove service/nginx, keep data
sudo /opt/directstream/deploy/server/vps/uninstall.sh --purge    # + wipe repo, venv, user, TLS cert(s)
```

(If you ran `install.sh` interactively, `uninstall.sh` reads back your
domain/client answers automatically from `/opt/directstream/.vps-deploy.env`
— no need to repeat `DOMAIN=...` etc.)

`--purge` asks for an explicit `YES` confirmation before deleting the repo
directory and before removing the service user — it won't silently destroy
anything.

## Known issues

- **`ffmpegAvailable: false` on `/health`**: ffmpeg is only used by
  auto-subtitles (`/transcribe`), not normal link extraction — so this can
  go unnoticed until someone actually generates subtitles. `install.sh`
  installs ffmpeg via `apt` automatically; if you skipped that or moved it,
  set `FFMPEG_BINARY`/`FFPROBE_BINARY` in `server/.env` to its absolute path
  (e.g. `/usr/bin/ffmpeg`) and restart.
- **"This site or URL isn't supported by the extractor" on a link that used
  to work**: usually means the pinned `yt-dlp`/`gallery-dl` version is
  behind — both sites (especially YouTube) change often enough that the
  version in `requirements.txt` can lag real fixes upstream. `update.sh`
  always upgrades both to their latest release, on top of the pinned
  versions — run it even if you haven't pulled new app code:
  `sudo /opt/directstream/deploy/server/vps/update.sh`
- **X/Twitter images: "No images found at this URL"**: most X content
  requires a logged-in session to even list — see **Server-wide cookies**
  above.
- **"Unknown or expired job" when generating subtitles**: this was a real
  bug (fixed) caused by running more than one backend worker process — the
  in-memory job list isn't shared between workers. If you're on an older
  install, re-run `install.sh` (or check `directstream.service`'s
  `--workers` flag is `1`, not `2`) and restart.

## Notes

- The security note in the root [`README.md`](../../../README.md) applies
  here too: `GET /proxy-video` fetches arbitrary user-supplied URLs with no
  host allow-list. On a public box, either restrict who can reach the
  service (firewall/VPN/auth in front) or add an allow-list before exposing
  it broadly.
- Want the client on a completely different host (Vercel/Netlify/Cloudflare
  Pages, not this box at all)? See [`../../client/vps/`](../../client/vps/)
  for that alternate path — `install.sh` above already covers same-box
  client hosting.

