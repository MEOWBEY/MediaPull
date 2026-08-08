#!/usr/bin/env bash
# One-time VPS provision (Debian/Ubuntu): packages, service user, clone, venv,
# systemd, nginx/TLS, firewall, optional client. Idempotent; safe to re-run.
#
# Interactive when stdin is a TTY. Answers land in /opt/mediapull/.vps-deploy.env
# for update.sh/uninstall.sh. Non-interactive:
#   sudo DOMAIN=api.example.com PORT=8000 CLIENT_MODE=same-domain ./install.sh
# Day-to-day deploys: use update.sh, not this script.
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
require_root

# ---- interactive prompts (skipped when var already set) -------------------
# No TTY (e.g. curl | bash) → defaults only, no hang on read.
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
  read -r -p "${C_CYAN}${question}${C_RESET}${C_DIM}${default:+ [$default]}${C_RESET}: " answer || true
  printf -v "$var" '%s' "${answer:-$default}"
  export "$var"
}

echo -e "${C_GREEN}==>${C_RESET} ${C_BOLD}MediaPull VPS installer${C_RESET}"
echo -e "    This sets up the backend and, if you want, the web client too."
echo -e "    Leave any answer blank to accept the default shown in ${C_DIM}[brackets]${C_RESET}."
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
      read -r -p "${C_CYAN}Public port for the reverse proxy?${C_RESET}${C_DIM} [80]${C_RESET}: " PUBLIC_PORT || true
      PUBLIC_PORT="${PUBLIC_PORT:-80}"
      if port_in_use "$PUBLIC_PORT"; then
        echo "    Something is already listening on port $PUBLIC_PORT -- this usually means"
        echo "    another panel or web server is already"
        echo "    using it. MediaPull will NOT touch it or overwrite its config."
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
# service from taking it all). Applied to mediapull.service below and re-applied
# by update.sh every deploy (it re-templates the unit already). 70% of RAM and
# (cores-1) worth of CPU -- leaves headroom for nginx/other panels on the same
# box. Computed in lib.sh (shared with update.sh); also exports
# CPU_CORES/MEM_TOTAL_MB for the small-box check below.
detect_resource_limits
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
  echo "  3) Don't serve it here -- I'm hosting it elsewhere or skipping it for now"
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
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  # Local-only sidecar; 4416 is its default. Only worth changing if something
  # else on the box already listens there. The app is pointed at whatever port
  # you pick via YOUTUBE_POT_BASE_URL below.
  ask POT_PORT "Port for the PO token provider (local sidecar)" "4416"
fi
POT_PORT="${POT_PORT:-4416}"

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

# GitHub auth: only a PRIVATE repo needs it. Ask ONCE and persist it into the
# checkout's remote (see persist_repo_auth), so this never re-prompts on a
# re-run and update.sh never prompts at all -- fixing the "asks 3 times for
# GitHub auth" problem. Skipped entirely when the checkout already has a saved
# credential, or for a public repo (blank token).
if [[ -d "$REPO_DIR/.git" ]] && remote_has_auth; then
  echo "==> repo already has a saved GitHub credential -- not asking again"
else
  ask GITHUB_TOKEN "GitHub access token (only for a PRIVATE repo; blank if it's public)" ""
fi

echo "==> fetching the repo into $REPO_DIR"
if [[ -d "$REPO_DIR/.git" ]]; then
  # Bring an existing checkout current (a re-run used to silently keep stale
  # code). chown first so the service-user git commands can touch .git/config.
  chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"
  persist_repo_auth "${GITHUB_TOKEN:-}"
  echo "    already cloned -- pulling latest"
  sync_repo || echo "    continuing with the existing checkout as-is (may miss recent fixes)." >&2
else
  GIT_TERMINAL_PROMPT=0 git clone "$(authed_url "$REPO_URL" "${GITHUB_TOKEN:-}")" "$REPO_DIR"
  chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"
  persist_repo_auth "${GITHUB_TOKEN:-}"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"

echo "==> setting up the Python venv"
sudo -u "$SERVICE_USER" "$PYTHON_BIN" -m venv "$REPO_DIR/server/venv"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade pip
install_backend_deps
# yt-dlp/gallery-dl move faster than this repo's pinned versions (sites like
# YouTube/Instagram/X change often) -- always grab the latest release of both
# on top of the pin, same as update.sh does on every subsequent update.
upgrade_scrapers

# ---- YouTube PO token provider (optional) ----------------------------------
# bgutil-ytdlp-pot-provider: a small Node.js companion service + a pip-
# installed yt-dlp plugin. yt-dlp auto-detects the plugin and talks to the
# service on its default port (127.0.0.1:4416) with zero extra config -- no
# extractor_args/env var needed on the app's side once both pieces are
# installed. Pinning both the plugin and the server to the SAME release tag
# matters -- the two speak a version-checked protocol and reject each other
# on a mismatch.
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  echo "==> installing the YouTube PO token provider (port $POT_PORT)"
  # sync_pot_provider_code (shared with update.sh) installs the pip plugin,
  # resolves its version, and clones+builds the matching Node server tag.
  if sync_pot_provider_code; then
    sync_pot_service "$POT_PORT"
    systemctl enable --now mediapull-pot
    echo "    PO token provider running as its own service (mediapull-pot), port $POT_PORT"
  else
    echo "    bgutil-ytdlp-pot-provider failed to install -- skipping the server half." >&2
    echo "    Set it up manually later: https://github.com/Brainicism/bgutil-ytdlp-pot-provider" >&2
    INSTALL_POT_PROVIDER="no"
  fi
fi

if [[ ! -f "$REPO_DIR/server/.env" ]]; then
  echo "==> creating server/.env from the production template (EDIT THIS AFTERWARDS)"
  sudo -u "$SERVICE_USER" cp "$REPO_DIR/server/.env.production.example" "$REPO_DIR/server/.env"
else
  echo "==> server/.env already exists, leaving it alone"
  # ...except for settings the app no longer has: scrub retired keys so a
  # re-run against an old install leaves a clean file (shared with update.sh).
  scrub_obsolete_env
fi
sudo -u "$SERVICE_USER" sed -i "s#^PORT=.*#PORT=$PORT#" "$REPO_DIR/server/.env"
if [[ -n "$GROQ_API_KEY" ]]; then
  sudo -u "$SERVICE_USER" sed -i "s#^GROQ_API_KEY=.*#GROQ_API_KEY=$GROQ_API_KEY#" "$REPO_DIR/server/.env"
fi
# Point yt-dlp's bgutil plugin at the provider's port (needed when it's not the
# 4416 the plugin auto-detects; harmless to set explicitly either way).
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  sudo -u "$SERVICE_USER" sed -i \
    "s#^YOUTUBE_POT_BASE_URL=.*#YOUTUBE_POT_BASE_URL=http://127.0.0.1:$POT_PORT#" \
    "$REPO_DIR/server/.env"
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
sudo -u "$SERVICE_USER" sed -i "s#^COOKIE_FILE_PATHS=.*#COOKIE_FILE_PATHS=$COOKIE_FILE_PATH#" "$REPO_DIR/server/.env"

# ---- client (optional) -----------------------------------------------------
CLIENT_DIR_SETTING=""
if [[ "$CLIENT_MODE" == "same-domain" ]]; then
  build_client same-domain
  CLIENT_DIR_SETTING="$REPO_DIR/client/build"
  sudo -u "$SERVICE_USER" sed -i "s#^CLIENT_DIR=.*#CLIENT_DIR=$CLIENT_DIR_SETTING#" "$REPO_DIR/server/.env"
elif [[ "$CLIENT_MODE" == "subdomain" ]]; then
  build_client subdomain "$DOMAIN"
  if [[ -n "$DOMAIN" ]]; then
    sudo -u "$SERVICE_USER" sed -i "s#^CORS_ORIGINS=.*#CORS_ORIGINS=https://$CLIENT_DOMAIN#" "$REPO_DIR/server/.env"
  fi
fi

echo "==> installing the systemd unit (port $PORT, MemoryMax=$MEMORY_MAX, CPUQuota=$CPU_QUOTA)"
sync_systemd_unit "$PORT" "$MEMORY_MAX" "$CPU_QUOTA"
systemctl enable --now "$SERVICE"

if [[ -n "$DOMAIN" ]]; then
  echo "==> configuring nginx for $DOMAIN (backend), public port $PUBLIC_PORT"
  sed "s/api.example.com/$DOMAIN/; s/__PORT__/$PORT/; s/__PUBLIC_PORT__/$PUBLIC_PORT/" \
    "$DEPLOY_DIR/nginx/backend.conf.example" \
    > "/etc/nginx/sites-available/$SERVICE-api"
  ln -sf "/etc/nginx/sites-available/$SERVICE-api" "/etc/nginx/sites-enabled/$SERVICE-api"
fi

if [[ "$CLIENT_MODE" == "subdomain" && -n "$CLIENT_DOMAIN" ]]; then
  echo "==> configuring nginx for $CLIENT_DOMAIN (client), public port $PUBLIC_PORT"
  sed "s/app.example.com/$CLIENT_DOMAIN/; s#__REPO_DIR__#$REPO_DIR#; s/__PUBLIC_PORT__/$PUBLIC_PORT/" \
    "$DEPLOY_DIR/nginx/client.conf.example" \
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

    # Open 80/443 in ufw BEFORE certbot, not after. Let's Encrypt's HTTP-01
    # challenge reaches this box on port 80 from the public internet, and the
    # issued cert then serves on 443 -- both must already be open when certbot
    # runs. The main firewall block further down hasn't executed yet at this
    # point, so on a box where ufw is already active (typically SSH-only),
    # certbot's challenge would be blocked and the whole install would fall
    # back to plain HTTP. Re-allowing the same ports later is harmless.
    if command -v ufw &>/dev/null && ufw status 2>/dev/null | grep -q "^Status: active"; then
      echo "    ufw is active -- opening ports 80 and 443 so the challenge can get through"
      ufw allow 80/tcp  || true
      ufw allow 443/tcp || true
    fi

    domains=()
    [[ -n "$DOMAIN" ]] && domains+=("$DOMAIN")
    [[ "$CLIENT_MODE" == "subdomain" && -n "${CLIENT_DOMAIN:-}" ]] && domains+=("$CLIENT_DOMAIN")
    for d in "${domains[@]}"; do
      if [[ -d "/etc/letsencrypt/live/$d" ]]; then
        echo "    certificate for $d already exists, skipping (run 'certbot renew' for renewals)"
        continue
      fi
      if ! certbot --nginx -d "$d" --non-interactive --agree-tos -m "admin@$d" --redirect; then
        echo "    certbot failed for $d -- the Let's Encrypt HTTP-01 challenge could not"
        echo "    reach this box on port 80. Check BOTH of these, then re-run the command"
        echo "    below:"
        echo "      1. DNS: '$d' must resolve to THIS server's public IP (dig +short $d)."
        echo "      2. Firewall: ports 80 AND 443 must be open to the internet -- not just"
        echo "         in ufw here, but in any cloud/provider firewall or security group"
        echo "         (AWS/GCP/Oracle/Hetzner block these by default)."
        echo "      Re-run once fixed:  certbot --nginx -d $d --redirect"
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
    # completely unrelated to MediaPull, like a control panel on its own port
    # (this has actually happened: installing the app silently took an
    # unrelated panel offline). Add the rules MediaPull needs (harmless either
    # way) but leave the decision to actually turn the firewall on to you,
    # since it affects the whole box, not just this app.
    echo "    ufw is currently inactive -- rules for MediaPull were added, but ufw"
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
POT_PORT=$POT_PORT
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
  echo "- PO token provider: enabled (systemd service mediapull-pot, 127.0.0.1:$POT_PORT)"
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
- PO token provider: running as its own service (mediapull-pot). Check it
  came up:
    systemctl status mediapull-pot
    journalctl -u mediapull-pot -n 50
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
    sudo $REPO_DIR/deploy/update.sh
- Remove everything later:
    sudo $REPO_DIR/deploy/uninstall.sh --purge
EOF
