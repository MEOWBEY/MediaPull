#!/usr/bin/env bash
# One-time provisioning for a fresh VPS (Debian/Ubuntu): system packages,
# service user, clone, venv, systemd unit, nginx + TLS, firewall -- and,
# if you want, the web client too (built + served from the same box).
# Idempotent -- safe to re-run if a step fails partway through.
#
# INTERACTIVE by default: run it with no arguments and it asks you a few
# questions (domain, port, whether to serve the client here too). Answer
# once; the answers are written to /opt/directstream/.vps-deploy.env so
# update.sh/uninstall.sh reuse them automatically later.
#
# For scripted/non-interactive installs (CI, a second box with the same
# answers), set the equivalent environment variables up front and they're
# used as-is with no prompt:
#   sudo DOMAIN=api.example.com PORT=8000 CLIENT_MODE=same-domain ./install.sh
#
# For routine "pull latest code and restart" after this has already run
# once, use update.sh instead -- this script is provisioning, not deploying.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/MEOWBEY/direct-stream.git}"
REPO_DIR="${REPO_DIR:-/opt/directstream}"
SERVICE_USER="${SERVICE_USER:-directstream}"
SERVICE="directstream"
CONFIG_FILE="$REPO_DIR/.vps-deploy.env"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

# ---- interactive prompts (skipped for any var already set in the env) -----
# Only prompts when connected to a real terminal (`sudo ./install.sh` run
# directly) AND the variable wasn't already provided via env -- piping the
# script through `curl | bash`, or any other non-terminal stdin, silently
# uses the defaults shown below instead of hanging waiting for input.
interactive=true
[[ -t 0 ]] || interactive=false

ask() {
  # ask VAR_NAME "question text" "default value"
  local var="$1" question="$2" default="${3:-}"
  local current="${!var:-}"
  if [[ -n "$current" ]]; then return; fi
  if ! $interactive; then
    printf -v "$var" '%s' "$default"
    export "$var"
    return
  fi
  local answer
  read -r -p "$question${default:+ [$default]}: " answer || true
  printf -v "$var" '%s' "${answer:-$default}"
  export "$var"
}

echo "==> DirectStream VPS installer"
echo "    This sets up the backend and, if you want, the web client too."
echo "    Leave any answer blank to accept the default shown in [brackets]."
echo

ask DOMAIN "What domain will the API use? (e.g. api.example.com -- blank skips HTTPS/nginx, service stays on 127.0.0.1 only)" ""
ask PORT "What port should the backend listen on?" "8000"

# Public-facing nginx port (only relevant once a domain is given -- with no
# domain, nginx/certbot are skipped entirely and the backend is only ever
# reached on 127.0.0.1:$PORT). Checked below for an existing listener before
# anything is written, so this installer doesn't silently steal a port
# another panel/web server on the same box is already using.
port_in_use() {
  # port_in_use PORT -- true if something is already listening on it.
  local check_port="$1"
  if command -v ss &>/dev/null; then
    ss -ltn "( sport = :$check_port )" 2>/dev/null | grep -q LISTEN
  elif command -v netstat &>/dev/null; then
    netstat -ltn 2>/dev/null | grep -q ":$check_port "
  else
    return 1
  fi
}

if [[ -n "$DOMAIN" ]]; then
  if [[ -n "${PUBLIC_PORT:-}" ]]; then
    # Already set via env (scripted/non-interactive run) -- warn but don't
    # loop asking for input that will never come.
    if port_in_use "$PUBLIC_PORT"; then
      echo "==> WARNING: port $PUBLIC_PORT (PUBLIC_PORT) already has a listener -- proceeding" >&2
      echo "    anyway since it was set explicitly for a non-interactive run." >&2
    fi
  elif ! $interactive; then
    PUBLIC_PORT="80"
  else
    while true; do
      read -r -p "Public port for the reverse proxy? [80]: " PUBLIC_PORT || true
      PUBLIC_PORT="${PUBLIC_PORT:-80}"
      if port_in_use "$PUBLIC_PORT"; then
        echo "    Something is already listening on port $PUBLIC_PORT -- this usually means"
        echo "    another panel or web server is already"
        echo "    using it. direct-stream will NOT touch it or overwrite its config."
        echo "    Pick a different port, or free this one up first."
        continue
      fi
      break
    done
  fi
else
  PUBLIC_PORT="${PUBLIC_PORT:-80}"
fi

# ---- resource limits (detected, not asked -- no need to bother the user) --
# Conservative caps so this app can't peg the box and starve nginx/other
# panels sharing it (a real VPS has hit ~90% CPU with nothing stopping this
# service from taking it all). Applied to directstream.service below and
# re-applied by update.sh every deploy (it re-templates the unit already).
CPU_CORES="$(nproc 2>/dev/null || echo 1)"
MEM_TOTAL_KB="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
MEM_TOTAL_MB=$(( MEM_TOTAL_KB / 1024 ))

# 70% of total RAM -- leaves headroom for nginx/other services/panels on the
# same box. Expressed in MB for systemd's MemoryMax=.
MEMORY_MAX_MB=$(( MEM_TOTAL_MB * 70 / 100 ))
[[ "$MEMORY_MAX_MB" -lt 1 ]] && MEMORY_MAX_MB=256
MEMORY_MAX="${MEMORY_MAX_MB}M"

# (cores - 1) * 100%, minimum 1 core's worth -- leaves roughly one core free
# rather than letting gunicorn/yt-dlp/ffmpeg saturate every core on the box.
CPU_QUOTA_CORES=$(( CPU_CORES - 1 ))
[[ "$CPU_QUOTA_CORES" -lt 1 ]] && CPU_QUOTA_CORES=1
CPU_QUOTA="$(( CPU_QUOTA_CORES * 100 ))%"

echo "==> detected ${CPU_CORES} CPU core(s), ${MEM_TOTAL_MB}MB RAM -- capping the service at" \
     "MemoryMax=$MEMORY_MAX, CPUQuota=$CPU_QUOTA"

# On a small box, also dial back the app's own concurrency defaults (2 each
# in code) so it doesn't oversubscribe a 1-2 core / <=2GB VPS -- otherwise
# leave unset so the code's built-in defaults apply.
SMALL_BOX=false
if [[ "$MEM_TOTAL_MB" -le 2048 || "$CPU_CORES" -le 2 ]]; then
  SMALL_BOX=true
  echo "    small box detected -- will cap TRANSCRIBE_MAX_CONCURRENT_JOBS/TRANSCRIBE_WORKERS at 1"
fi

if [[ -z "${CLIENT_MODE:-}" ]]; then
  echo
  echo "How do you want to serve the web client (the browser UI)?"
  echo "  1) Same domain as the API -- simplest, one origin, no CORS to configure"
  echo "  2) A separate subdomain on this same server (e.g. app.example.com)"
  echo "  3) Don't serve it here -- I'm hosting it elsewhere (Vercel/Netlify/etc.) or skipping it for now"
  ask CLIENT_CHOICE "Choice" "1"
  case "$CLIENT_CHOICE" in
    2) CLIENT_MODE="subdomain" ;;
    3) CLIENT_MODE="none" ;;
    *) CLIENT_MODE="same-domain" ;;
  esac
fi

if [[ "$CLIENT_MODE" == "subdomain" ]]; then
  ask CLIENT_DOMAIN "What domain will the client use? (e.g. app.example.com)" ""
fi

echo
echo "YouTube increasingly requires a 'PO token' to prove requests aren't"
echo "automated -- without one you'll see errors like 'Sign in to confirm"
echo "you're not a bot' or age-restricted videos refusing to extract, even"
echo "with cookies added. A small companion service can fetch these"
echo "automatically per-video (the manual-extraction method is deprecated"
echo "and stops working per-video anyway)."
ask INSTALL_POT_PROVIDER "Install the PO token provider for YouTube? (recommended) [Y/n]" "Y"
case "${INSTALL_POT_PROVIDER,,}" in
  n|no) INSTALL_POT_PROVIDER="no" ;;
  *) INSTALL_POT_PROVIDER="yes" ;;
esac

echo
echo "Auto-subtitles (speech-to-text via Groq's free Whisper API) need a Groq"
echo "API key. Get one free, no card required, at https://console.groq.com"
echo "Leave blank to skip -- you can add it to server/.env later and restart."
ask GROQ_API_KEY "Groq API key" ""

echo
echo "==> installing system packages"
apt-get update
apt-get install -y ffmpeg nginx git curl ca-certificates

# Python: prefer 3.12, but fall back through whatever this distro's default
# repos actually offer -- Ubuntu 22.04 "jammy" only ships up to 3.10 without
# a third-party PPA, Debian 12 ships 3.11, etc. Nothing in this app needs
# 3.12 specifically (no match-statement/PEP 695 syntax used), so hard-failing
# on a single minor version here was a real bug, not a real requirement.
PYTHON_BIN=""
for cand in python3.12 python3.11 python3.10 python3; do
  if apt-cache show "$cand" &>/dev/null 2>&1 || command -v "$cand" &>/dev/null; then
    PYTHON_BIN="$cand"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "No usable Python 3.10+ found or installable via apt on this system." >&2
  echo "Install Python 3.10+ manually (e.g. via the deadsnakes PPA on Ubuntu), then re-run." >&2
  exit 1
fi
VENV_PKG="${PYTHON_BIN}-venv"
[[ "$PYTHON_BIN" == "python3" ]] && VENV_PKG="python3-venv"
apt-get install -y "$PYTHON_BIN" "$VENV_PKG"
echo "==> using $PYTHON_BIN ($("$PYTHON_BIN" --version 2>&1))"

if [[ "$CLIENT_MODE" != "none" || "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  if ! command -v node &>/dev/null || [[ "$(node -v | sed 's/^v//;s/\..*//')" -lt 22 ]]; then
    echo "==> installing Node.js 22.x (needed to build the client and/or the PO token provider)"
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
  fi
fi

echo "==> creating service user '$SERVICE_USER' (if missing)"
id -u "$SERVICE_USER" &>/dev/null || \
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"

echo "==> fetching the repo into $REPO_DIR"
if [[ -d "$REPO_DIR/.git" ]]; then
  # Re-running install.sh on a box that already has a checkout (e.g. to pick
  # up a new release) used to just reuse whatever was cloned the first time,
  # forever -- silently working from stale code with no error, until a step
  # later on referenced a file/flag that didn't exist yet in that old
  # checkout. Bring it current the same way update.sh does before relying on
  # anything from it below.
  # Run as SERVICE_USER, not root -- the checkout is normally owned by it
  # (chown'd below on every run), and a root-owned git command against a
  # directory owned by someone else trips git's "dubious ownership" guard.
  branch="$(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD")"
  if [[ "$branch" == "HEAD" ]]; then
    echo "    $REPO_DIR is in a detached HEAD state -- leaving it as-is." >&2
    echo "    Run 'cd $REPO_DIR && git checkout main && git pull' yourself first for the latest code." >&2
  else
    echo "    already cloned -- pulling latest ($branch)"
    sudo -u "$SERVICE_USER" git -C "$REPO_DIR" fetch origin
    if ! sudo -u "$SERVICE_USER" git -C "$REPO_DIR" pull --ff-only origin "$branch"; then
      echo "    WARNING: git pull failed (local edits or diverged history?) -- continuing with" >&2
      echo "    the existing checkout as-is, which may be missing recent fixes." >&2
    fi
  fi
else
  git clone "$REPO_URL" "$REPO_DIR"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"

echo "==> setting up the Python venv"
sudo -u "$SERVICE_USER" "$PYTHON_BIN" -m venv "$REPO_DIR/server/venv"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install -r "$REPO_DIR/server/requirements.txt"
# yt-dlp/gallery-dl move faster than this repo's pinned versions (sites like
# YouTube/Instagram/X change often) -- always grab the latest release of both
# on top of the pin, same as update.sh does on every subsequent update.
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade yt-dlp gallery-dl

# ---- YouTube PO token provider (optional) ----------------------------------
# bgutil-ytdlp-pot-provider: a small Node.js companion service + a pip-
# installed yt-dlp plugin. yt-dlp auto-detects the plugin and talks to the
# service on its default port (127.0.0.1:4416) with zero extra config -- no
# extractor_args/env var needed on the app's side once both pieces are
# installed. Pinning both the plugin and the server to the SAME release tag
# matters -- the two speak a version-checked protocol and reject each other
# on a mismatch.
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  echo "==> installing the YouTube PO token provider"
  sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade bgutil-ytdlp-pot-provider
  # Read back whatever version pip actually resolved, so the server clone
  # below matches it exactly rather than guessing/hardcoding a tag.
  POT_VERSION="$(sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" show bgutil-ytdlp-pot-provider 2>/dev/null | sed -n 's/^Version: //p')"
  if [[ -z "$POT_VERSION" ]]; then
    echo "    bgutil-ytdlp-pot-provider failed to install -- skipping the server half." >&2
    echo "    Set it up manually later: https://github.com/Brainicism/bgutil-ytdlp-pot-provider" >&2
  else
    POT_DIR="$REPO_DIR/pot-provider"
    if [[ -d "$POT_DIR/.git" ]]; then
      echo "    $POT_DIR already cloned, skipping"
    else
      sudo -u "$SERVICE_USER" git clone --single-branch --branch "$POT_VERSION" \
        https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$POT_DIR"
    fi
    sudo -u "$SERVICE_USER" bash -c "cd '$POT_DIR/server' && npm ci && npx tsc"

    sed "s#__REPO_DIR__#$REPO_DIR#; s#__SERVICE_USER__#$SERVICE_USER#" \
      "$REPO_DIR/deploy/server/vps/directstream-pot.service" \
      > /etc/systemd/system/directstream-pot.service
    systemctl daemon-reload
    systemctl enable --now directstream-pot
    echo "    PO token provider running as its own service (directstream-pot), port 4416"
  fi
fi

ask YOUTUBE_PO_TOKEN "Static YouTube PO token (optional manual override, leave blank to rely on the automatic provider -- most people should leave this blank)" ""

if [[ ! -f "$REPO_DIR/server/.env" ]]; then
  echo "==> creating server/.env from the production template (EDIT THIS AFTERWARDS)"
  sudo -u "$SERVICE_USER" cp "$REPO_DIR/server/.env.production.example" "$REPO_DIR/server/.env"
else
  echo "==> server/.env already exists, leaving it alone"
fi
sudo -u "$SERVICE_USER" sed -i "s#^PORT=.*#PORT=$PORT#" "$REPO_DIR/server/.env"
if [[ -n "$GROQ_API_KEY" ]]; then
  sudo -u "$SERVICE_USER" sed -i "s#^GROQ_API_KEY=.*#GROQ_API_KEY=$GROQ_API_KEY#" "$REPO_DIR/server/.env"
fi
if [[ -n "$YOUTUBE_PO_TOKEN" ]]; then
  sudo -u "$SERVICE_USER" sed -i "s#^YOUTUBE_PO_TOKEN=.*#YOUTUBE_PO_TOKEN=$YOUTUBE_PO_TOKEN#" "$REPO_DIR/server/.env"
fi
if [[ "$SMALL_BOX" == true ]]; then
  sudo -u "$SERVICE_USER" sed -i \
    -e "s#^TRANSCRIBE_MAX_CONCURRENT_JOBS=.*#TRANSCRIBE_MAX_CONCURRENT_JOBS=1#" \
    -e "s#^TRANSCRIBE_WORKERS=.*#TRANSCRIBE_WORKERS=1#" \
    "$REPO_DIR/server/.env"
fi

# Server-wide default cookies file: many sites (YouTube age-gates, most of
# X/Twitter, private/login-only Instagram posts) refuse to serve content at
# all without a logged-in session. Same pattern as server/.env above -- copy
# the tracked example once, then it's yours to edit; update.sh/uninstall.sh
# never touch it, so pasting real cookies in survives every future update.
COOKIE_FILE_PATH="$REPO_DIR/server/cookies.txt"
if [[ ! -f "$COOKIE_FILE_PATH" ]]; then
  echo "==> creating server/cookies.txt from the template (paste your real cookies in afterwards)"
  sudo -u "$SERVICE_USER" cp "$REPO_DIR/server/cookies.example.txt" "$COOKIE_FILE_PATH"
  chmod 600 "$COOKIE_FILE_PATH"
else
  echo "==> $COOKIE_FILE_PATH already exists, leaving it alone"
fi
sudo -u "$SERVICE_USER" sed -i "s#^COOKIE_FILE=.*#COOKIE_FILE=$COOKIE_FILE_PATH#" "$REPO_DIR/server/.env"

# ---- client (optional) -----------------------------------------------------
CLIENT_DIR_SETTING=""
if [[ "$CLIENT_MODE" == "same-domain" ]]; then
  echo "==> building the client for combined single-origin serving"
  sudo -u "$SERVICE_USER" bash -c "cd '$REPO_DIR/client' && npm ci && npm run build"
  CLIENT_DIR_SETTING="$REPO_DIR/client/build"
  sudo -u "$SERVICE_USER" sed -i "s#^CLIENT_DIR=.*#CLIENT_DIR=$CLIENT_DIR_SETTING#" "$REPO_DIR/server/.env"
elif [[ "$CLIENT_MODE" == "subdomain" ]]; then
  echo "==> building the client for its own subdomain ($CLIENT_DOMAIN)"
  sudo -u "$SERVICE_USER" bash -c \
    "cd '$REPO_DIR/client' && VITE_API_BASE_URL='https://$DOMAIN' npm ci && npm run build"
  if [[ -n "$DOMAIN" ]]; then
    sudo -u "$SERVICE_USER" sed -i "s#^CORS_ORIGINS=.*#CORS_ORIGINS=https://$CLIENT_DOMAIN#" "$REPO_DIR/server/.env"
  fi
fi

echo "==> installing the systemd unit (port $PORT, MemoryMax=$MEMORY_MAX, CPUQuota=$CPU_QUOTA)"
sed "s/__PORT__/$PORT/; s/__MEMORY_MAX__/$MEMORY_MAX/; s/__CPU_QUOTA__/$CPU_QUOTA/" \
  "$REPO_DIR/deploy/server/vps/directstream.service" \
  > /etc/systemd/system/directstream.service
systemctl daemon-reload
systemctl enable --now "$SERVICE"

if [[ -n "$DOMAIN" ]]; then
  echo "==> configuring nginx for $DOMAIN (backend), public port $PUBLIC_PORT"
  sed "s/api.example.com/$DOMAIN/; s/__PORT__/$PORT/; s/__PUBLIC_PORT__/$PUBLIC_PORT/" \
    "$REPO_DIR/deploy/server/vps/nginx-backend.conf.example" \
    > "/etc/nginx/sites-available/$SERVICE-api"
  ln -sf "/etc/nginx/sites-available/$SERVICE-api" "/etc/nginx/sites-enabled/$SERVICE-api"
fi

if [[ "$CLIENT_MODE" == "subdomain" && -n "$CLIENT_DOMAIN" ]]; then
  echo "==> configuring nginx for $CLIENT_DOMAIN (client), public port $PUBLIC_PORT"
  sed "s/app.example.com/$CLIENT_DOMAIN/; s#/opt/directstream#$REPO_DIR#; s/__PUBLIC_PORT__/$PUBLIC_PORT/" \
    "$REPO_DIR/deploy/client/vps/nginx-client.conf.example" \
    > "/etc/nginx/sites-available/$SERVICE-client"
  ln -sf "/etc/nginx/sites-available/$SERVICE-client" "/etc/nginx/sites-enabled/$SERVICE-client"
fi

tls_ok=true
tls_attempted=false
if [[ -n "$DOMAIN" || ( "$CLIENT_MODE" == "subdomain" && -n "${CLIENT_DOMAIN:-}" ) ]]; then
  nginx -t && systemctl reload nginx

  # Let's Encrypt's HTTP-01 challenge always needs port 80 itself, however
  # briefly, regardless of what $PUBLIC_PORT the site actually serves on --
  # if something else already owns 80, skip certbot automatically instead of
  # failing the whole install; the site still comes up fine on $PUBLIC_PORT
  # over plain HTTP in that case.
  if [[ "$PUBLIC_PORT" != "80" && "$PUBLIC_PORT" != "443" ]] && port_in_use 80; then
    echo "==> WARNING: port 80 is already in use, and TLS setup needs it briefly for the"
    echo "    Let's Encrypt HTTP-01 challenge (independent of the $PUBLIC_PORT this site"
    echo "    serves on). Skipping certbot -- the site will run on plain HTTP for now."
    echo "    Get a certificate manually later once port 80 is free, e.g.:"
    echo "      certbot certonly --standalone -d $DOMAIN"
    tls_ok=false
  else
    tls_attempted=true
    echo "==> requesting TLS certificate(s) (certbot)"
    apt-get install -y certbot python3-certbot-nginx
    domains=()
    [[ -n "$DOMAIN" ]] && domains+=("$DOMAIN")
    [[ "$CLIENT_MODE" == "subdomain" && -n "${CLIENT_DOMAIN:-}" ]] && domains+=("$CLIENT_DOMAIN")
    for d in "${domains[@]}"; do
      if [[ -d "/etc/letsencrypt/live/$d" ]]; then
        echo "    certificate for $d already exists, skipping (run 'certbot renew' for renewals)"
        continue
      fi
      if ! certbot --nginx -d "$d" --non-interactive --agree-tos -m "admin@$d" --redirect; then
        echo "    certbot failed/skipped for $d -- DNS may not point here yet."
        echo "    Re-run later: certbot --nginx -d $d"
        tls_ok=false
      fi
    done
  fi
else
  echo "==> no domain given -- skipping nginx/certbot. Backend reachable at 127.0.0.1:$PORT only."
fi

echo "==> configuring the firewall (ufw)"
UFW_WAS_ACTIVE=false
if command -v ufw &>/dev/null; then
  ufw status 2>/dev/null | grep -q "^Status: active" && UFW_WAS_ACTIVE=true
  ufw allow OpenSSH || true
  if [[ -n "$DOMAIN" || "$CLIENT_MODE" == "subdomain" ]]; then
    if [[ "$PUBLIC_PORT" == "80" ]]; then
      ufw allow 'Nginx Full' || true
    else
      ufw allow "$PUBLIC_PORT"/tcp || true
      [[ "$tls_attempted" == true ]] && { ufw allow 443/tcp || true; }
    fi
  fi
  if $UFW_WAS_ACTIVE; then
    # Already your policy before we got here -- just adding to it is safe.
    ufw --force enable >/dev/null
  else
    # Force-enabling an INACTIVE firewall here would block every other port
    # on this box that isn't explicitly allowed -- including things
    # completely unrelated to direct-stream, like a control panel on its own
    # port (this has actually happened: installing direct-stream silently
    # took an unrelated panel offline). Add the rules direct-stream needs
    # (harmless either way) but leave the decision to actually turn the
    # firewall on to you, since it affects the whole box, not just this app.
    echo "    ufw is currently inactive -- rules for direct-stream were added, but ufw"
    echo "    itself was NOT enabled (enabling it would also block any other port on"
    echo "    this box you haven't explicitly allowed yet, e.g. a control panel)."
    echo "    If you want a firewall: run 'ufw allow <port>/tcp' for anything else you"
    echo "    use (SSH is already allowed), then 'ufw enable' yourself."
  fi
else
  echo "    ufw not installed, skipping"
fi

echo "==> saving your answers to $CONFIG_FILE (used by update.sh/uninstall.sh)"
cat > "$CONFIG_FILE" <<EOF
REPO_DIR=$REPO_DIR
SERVICE_USER=$SERVICE_USER
PORT=$PORT
DOMAIN=$DOMAIN
PUBLIC_PORT=${PUBLIC_PORT:-80}
CLIENT_MODE=$CLIENT_MODE
CLIENT_DOMAIN=${CLIENT_DOMAIN:-}
INSTALL_POT_PROVIDER=$INSTALL_POT_PROVIDER
UFW_WAS_ACTIVE=$UFW_WAS_ACTIVE
MEMORY_MAX=$MEMORY_MAX
CPU_QUOTA=$CPU_QUOTA
EOF
chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_FILE"

echo "==> verifying"
sleep 2
if curl -fsS "http://127.0.0.1:$PORT/health"; then
  echo " backend OK"
else
  echo " backend did NOT respond on 127.0.0.1:$PORT -- check: journalctl -u $SERVICE -n 50"
fi

cat <<EOF

Done.
- Edit $REPO_DIR/server/.env for anything beyond what you already answered
  (proxy, YouTube player clients, etc.), then:
    systemctl restart $SERVICE
EOF
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  echo "- PO token provider: enabled (systemd service directstream-pot, 127.0.0.1:4416)"
else
  echo "- PO token provider: not installed -- YouTube extraction may get blocked more often"
fi
if [[ -z "$GROQ_API_KEY" ]]; then
  cat <<EOF
- Auto-subtitles are OFF (no Groq API key given). Get a free key at
  https://console.groq.com, then:
    sudo nano $REPO_DIR/server/.env   # set GROQ_API_KEY=...
    systemctl restart $SERVICE
EOF
fi
cat <<EOF
- Add cookies (recommended -- unlocks YouTube age-gates, most X/Twitter
  content, and private Instagram posts for everyone using this server):
    sudo nano $COOKIE_FILE_PATH
  Paste Netscape-format cookies.txt content (e.g. exported via the
  "Get cookies.txt LOCALLY" browser extension), save, then:
    systemctl restart $SERVICE
  This file is never touched by update.sh/uninstall.sh, so it survives
  every future update.
- Check ffmpeg/gallery-dl are actually reachable:
    curl http://127.0.0.1:$PORT/health   (look for "ffmpegAvailable"/"galleryDlAvailable": true)
EOF
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  cat <<EOF
- PO token provider: running as its own service (directstream-pot). Check it
  came up:
    systemctl status directstream-pot
    journalctl -u directstream-pot -n 50
EOF
fi
if ! $tls_ok; then
  cat <<EOF
- TLS wasn't fully set up for every domain above -- point DNS at this
  server's IP if you haven't yet, then re-run the certbot command shown.
EOF
fi
cat <<EOF
- Routine updates from now on (pulls code, rebuilds the client if you
  installed one, restarts, health-checks):
    sudo $REPO_DIR/deploy/server/vps/update.sh
- Remove everything later:
    sudo $REPO_DIR/deploy/server/vps/uninstall.sh --purge
EOF
