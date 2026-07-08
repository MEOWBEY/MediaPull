#!/usr/bin/env bash
# Reverses install.sh. By default only stops/disables the service and
# removes the nginx site(s) (safe, non-destructive to your data/config).
# Pass --purge to also delete the cloned repo, venv, the service user, and
# the TLS certificate(s).
#
# Usage (as root or via sudo):
#   sudo ./uninstall.sh              # stop + remove service/nginx only
#   sudo ./uninstall.sh --purge      # also wipe everything (asks to confirm)
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/directstream}"
SERVICE_USER="${SERVICE_USER:-directstream}"
SERVICE="directstream"
DOMAIN="${DOMAIN:-}"
CLIENT_MODE="${CLIENT_MODE:-none}"
CLIENT_DOMAIN="${CLIENT_DOMAIN:-}"
CONFIG_FILE="$REPO_DIR/.vps-deploy.env"
PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source <(grep -v '^\s*#' "$CONFIG_FILE")
fi

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

echo "==> stopping and disabling the service"
systemctl stop "$SERVICE" 2>/dev/null || true
systemctl disable "$SERVICE" 2>/dev/null || true
rm -f "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload

echo "==> removing the nginx site(s) (if present)"
rm -f "/etc/nginx/sites-enabled/$SERVICE-api" "/etc/nginx/sites-available/$SERVICE-api"
rm -f "/etc/nginx/sites-enabled/$SERVICE-client" "/etc/nginx/sites-available/$SERVICE-client"
if command -v nginx &>/dev/null; then
  nginx -t 2>/dev/null && systemctl reload nginx || echo "    (nginx not reloaded — check config)"
fi

echo "==> removing firewall rules added by install.sh (if ufw is in use)"
if command -v ufw &>/dev/null; then
  if [[ -n "$DOMAIN" || "$CLIENT_MODE" == "subdomain" ]]; then
    ufw delete allow 'Nginx Full' 2>/dev/null || true
  fi
fi

if ! $PURGE; then
  cat <<EOF

Service and nginx site(s) removed. Left in place (re-run with --purge to remove):
  - $REPO_DIR (repo, venv, server/.env, client/build)
  - system user '$SERVICE_USER'
  - TLS certificate(s) for ${DOMAIN:-<none>} ${CLIENT_DOMAIN:+and $CLIENT_DOMAIN}
  - the 'OpenSSH' ufw rule (left alone on purpose -- don't lock yourself out)
EOF
  exit 0
fi

echo "==> --purge: removing TLS certificate(s)"
if command -v certbot &>/dev/null; then
  [[ -n "$DOMAIN" ]] && certbot delete --cert-name "$DOMAIN" --non-interactive 2>/dev/null || true
  [[ -n "$CLIENT_DOMAIN" ]] && certbot delete --cert-name "$CLIENT_DOMAIN" --non-interactive 2>/dev/null || true
else
  echo "    certbot not installed, skipping"
fi

echo "==> --purge: this will permanently delete $REPO_DIR (repo, venv, .env, any cookies.txt in it)"
read -r -p "    type YES to confirm: " confirm
if [[ "$confirm" == "YES" ]]; then
  rm -rf "$REPO_DIR"
else
  echo "    skipped — $REPO_DIR left in place"
fi

echo "==> --purge: removing service user '$SERVICE_USER'"
read -r -p "    type YES to confirm: " confirm_user
if [[ "$confirm_user" == "YES" ]]; then
  userdel "$SERVICE_USER" 2>/dev/null || true
else
  echo "    skipped — user left in place"
fi

echo "==> done"
