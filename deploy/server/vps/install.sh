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

if [[ "$CLIENT_MODE" != "none" ]]; then
  if ! command -v node &>/dev/null || [[ "$(node -v | sed 's/^v//;s/\..*//')" -lt 22 ]]; then
    echo "==> installing Node.js 22.x (needed to build the client)"
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt-get install -y nodejs
  fi
fi

echo "==> creating service user '$SERVICE_USER' (if missing)"
id -u "$SERVICE_USER" &>/dev/null || \
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"

echo "==> fetching the repo into $REPO_DIR"
if [[ -d "$REPO_DIR/.git" ]]; then
  echo "    already cloned, skipping"
else
  git clone "$REPO_URL" "$REPO_DIR"
fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$REPO_DIR"

echo "==> setting up the Python venv"
sudo -u "$SERVICE_USER" "$PYTHON_BIN" -m venv "$REPO_DIR/server/venv"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install -r "$REPO_DIR/server/requirements.txt"

if [[ ! -f "$REPO_DIR/server/.env" ]]; then
  echo "==> creating server/.env from the production template (EDIT THIS AFTERWARDS)"
  sudo -u "$SERVICE_USER" cp "$REPO_DIR/server/.env.production.example" "$REPO_DIR/server/.env"
else
  echo "==> server/.env already exists, leaving it alone"
fi
sudo -u "$SERVICE_USER" sed -i "s#^PORT=.*#PORT=$PORT#" "$REPO_DIR/server/.env"

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

echo "==> installing the systemd unit (port $PORT)"
sed "s/__PORT__/$PORT/" "$REPO_DIR/deploy/server/vps/directstream.service" \
  > /etc/systemd/system/directstream.service
systemctl daemon-reload
systemctl enable --now "$SERVICE"

if [[ -n "$DOMAIN" ]]; then
  echo "==> configuring nginx for $DOMAIN (backend)"
  sed "s/api.example.com/$DOMAIN/; s/__PORT__/$PORT/" \
    "$REPO_DIR/deploy/server/vps/nginx-backend.conf.example" \
    > "/etc/nginx/sites-available/$SERVICE-api"
  ln -sf "/etc/nginx/sites-available/$SERVICE-api" "/etc/nginx/sites-enabled/$SERVICE-api"
fi

if [[ "$CLIENT_MODE" == "subdomain" && -n "$CLIENT_DOMAIN" ]]; then
  echo "==> configuring nginx for $CLIENT_DOMAIN (client)"
  sed "s/app.example.com/$CLIENT_DOMAIN/; s#/opt/directstream#$REPO_DIR#" \
    "$REPO_DIR/deploy/client/vps/nginx-client.conf.example" \
    > "/etc/nginx/sites-available/$SERVICE-client"
  ln -sf "/etc/nginx/sites-available/$SERVICE-client" "/etc/nginx/sites-enabled/$SERVICE-client"
fi

tls_ok=true
if [[ -n "$DOMAIN" || ( "$CLIENT_MODE" == "subdomain" && -n "${CLIENT_DOMAIN:-}" ) ]]; then
  nginx -t && systemctl reload nginx

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
else
  echo "==> no domain given -- skipping nginx/certbot. Backend reachable at 127.0.0.1:$PORT only."
fi

echo "==> configuring the firewall (ufw)"
if command -v ufw &>/dev/null; then
  ufw allow OpenSSH || true
  if [[ -n "$DOMAIN" || "$CLIENT_MODE" == "subdomain" ]]; then
    ufw allow 'Nginx Full' || true
  fi
  ufw --force enable
else
  echo "    ufw not installed, skipping"
fi

echo "==> saving your answers to $CONFIG_FILE (used by update.sh/uninstall.sh)"
cat > "$CONFIG_FILE" <<EOF
REPO_DIR=$REPO_DIR
SERVICE_USER=$SERVICE_USER
PORT=$PORT
DOMAIN=$DOMAIN
CLIENT_MODE=$CLIENT_MODE
CLIENT_DOMAIN=${CLIENT_DOMAIN:-}
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
- Edit $REPO_DIR/server/.env for cookies/proxy/YouTube/Groq (auto-subtitles) knobs, then:
    systemctl restart $SERVICE
- Check ffmpeg/gallery-dl are actually reachable:
    curl http://127.0.0.1:$PORT/health   (look for "ffmpegAvailable"/"galleryDlAvailable": true)
EOF
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
