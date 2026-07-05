#!/usr/bin/env bash
# Reverses install.sh. By default only stops/disables the service and
# removes the systemd unit + nginx site (safe, non-destructive to your
# data/config). Pass --purge to also delete the cloned repo, venv, the
# service user, and the TLS certificate.
#
# Usage (as root or via sudo):
#   sudo ./uninstall.sh                          # stop + remove service/nginx only
#   sudo DOMAIN=api.example.com ./uninstall.sh --purge   # also wipe everything
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/directstream}"
SERVICE_USER="${SERVICE_USER:-directstream}"
SERVICE="directstream"
DOMAIN="${DOMAIN:-}"
PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (or with sudo)." >&2
  exit 1
fi

echo "==> stopping and disabling the service"
systemctl stop "$SERVICE" 2>/dev/null || true
systemctl disable "$SERVICE" 2>/dev/null || true
rm -f "/etc/systemd/system/$SERVICE.service"
systemctl daemon-reload

echo "==> removing the nginx site (if present)"
rm -f "/etc/nginx/sites-enabled/$SERVICE-api" "/etc/nginx/sites-available/$SERVICE-api"
if command -v nginx &>/dev/null; then
  nginx -t 2>/dev/null && systemctl reload nginx || echo "    (nginx not reloaded — check config)"
fi

if ! $PURGE; then
  cat <<EOF

Service and nginx site removed. Left in place (re-run with --purge to remove):
  - $REPO_DIR (repo, venv, server/.env)
  - system user '$SERVICE_USER'
  - TLS certificate for ${DOMAIN:-<none given>}
EOF
  exit 0
fi

echo "==> --purge: removing the TLS certificate"
if [[ -n "$DOMAIN" ]] && command -v certbot &>/dev/null; then
  certbot delete --cert-name "$DOMAIN" --non-interactive || true
else
  echo "    no DOMAIN given or certbot not installed, skipping"
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
