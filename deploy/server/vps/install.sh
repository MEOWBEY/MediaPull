#!/usr/bin/env bash
# One-time backend provisioning for a fresh VPS (Debian/Ubuntu): system
# packages, service user, clone, venv, systemd unit, nginx + TLS, firewall.
# Idempotent — safe to re-run if a step fails partway through.
#
# For routine "pull latest code and restart" after this has already run
# once, use update.sh instead — this script is provisioning, not deploying.
#
# Usage (as root or via sudo):
#   sudo DOMAIN=api.example.com ./install.sh
#   sudo DOMAIN=api.example.com REPO_URL=git@github.com:you/your-fork.git ./install.sh
#
# DOMAIN is optional — omit it to skip nginx/certbot and just get the
# service running on 127.0.0.1:8000 (add a reverse proxy yourself later).
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/MEOWBEY/direct-stream.git}"
REPO_DIR="${REPO_DIR:-/opt/directstream}"
SERVICE_USER="${SERVICE_USER:-directstream}"
SERVICE="directstream"
DOMAIN="${DOMAIN:-}"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

echo "==> installing system packages"
apt-get update
apt-get install -y python3.12 python3.12-venv ffmpeg nginx git curl

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
sudo -u "$SERVICE_USER" python3.12 -m venv "$REPO_DIR/server/venv"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install -r "$REPO_DIR/server/requirements.txt"

if [[ ! -f "$REPO_DIR/server/.env" ]]; then
  echo "==> creating server/.env from the production template (EDIT THIS AFTERWARDS)"
  sudo -u "$SERVICE_USER" cp "$REPO_DIR/server/.env.production.example" "$REPO_DIR/server/.env"
  if [[ -n "$DOMAIN" ]]; then
    sudo -u "$SERVICE_USER" sed -i "s#^CORS_ORIGINS=.*#CORS_ORIGINS=https://$DOMAIN#" "$REPO_DIR/server/.env"
  fi
else
  echo "==> server/.env already exists, leaving it alone"
fi

echo "==> installing the systemd unit"
cp "$REPO_DIR/deploy/server/vps/directstream.service" /etc/systemd/system/directstream.service
systemctl daemon-reload
systemctl enable --now "$SERVICE"

if [[ -n "$DOMAIN" ]]; then
  echo "==> configuring nginx for $DOMAIN"
  sed "s/api.example.com/$DOMAIN/" \
    "$REPO_DIR/deploy/server/vps/nginx-backend.conf.example" \
    > "/etc/nginx/sites-available/$SERVICE-api"
  ln -sf "/etc/nginx/sites-available/$SERVICE-api" "/etc/nginx/sites-enabled/$SERVICE-api"
  nginx -t && systemctl reload nginx

  echo "==> requesting a TLS certificate (certbot)"
  apt-get install -y certbot python3-certbot-nginx
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "admin@$DOMAIN" --redirect || \
    echo "    certbot failed/skipped — DNS may not point here yet; re-run: certbot --nginx -d $DOMAIN"
else
  echo "==> DOMAIN not set — skipping nginx/certbot. Service is reachable at 127.0.0.1:8000 only."
fi

echo "==> configuring the firewall (ufw)"
if command -v ufw &>/dev/null; then
  ufw allow OpenSSH || true
  [[ -n "$DOMAIN" ]] && ufw allow 'Nginx Full' || true
  ufw --force enable
else
  echo "    ufw not installed, skipping"
fi

echo "==> verifying"
sleep 2
curl -fsS http://127.0.0.1:8000/health && echo " backend OK"

cat <<EOF

Done.
- Edit $REPO_DIR/server/.env for cookies/proxy/YouTube knobs, then:
    systemctl restart $SERVICE
- Routine updates from now on: sudo $REPO_DIR/deploy/server/vps/update.sh
- Client: see $REPO_DIR/deploy/client/vps/README.md
EOF
