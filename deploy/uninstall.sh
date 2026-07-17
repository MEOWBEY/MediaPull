#!/usr/bin/env bash
# Reverse install.sh: stop service + remove nginx sites.
#   sudo ./uninstall.sh           # keep repo/venv/user
#   sudo ./uninstall.sh --purge   # also wipe data (asks YES)
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# Defaults; overridden by install.sh's saved CONFIG_FILE when present.
DOMAIN="${DOMAIN:-}"
CLIENT_MODE="${CLIENT_MODE:-none}"
CLIENT_DOMAIN="${CLIENT_DOMAIN:-}"
PUBLIC_PORT="${PUBLIC_PORT:-80}"
# Unset (not true/false) on a .vps-deploy.env written before this field
# existed -- treated as "unknown" below, not "false", since we genuinely
# don't know whether ufw was already on before install.sh ran on an older
# install and don't want to claim otherwise.
UFW_WAS_ACTIVE="${UFW_WAS_ACTIVE:-}"
PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

require_root
load_config

echo "==> stopping and disabling the service"
systemctl stop "$SERVICE" 2>/dev/null || true
systemctl disable "$SERVICE" 2>/dev/null || true
rm -f "/etc/systemd/system/$SERVICE.service"

echo "==> stopping and disabling the PO token provider (if installed)"
systemctl stop mediapull-pot 2>/dev/null || true
systemctl disable mediapull-pot 2>/dev/null || true
rm -f /etc/systemd/system/mediapull-pot.service

systemctl daemon-reload

echo "==> removing the nginx site(s) (if present)"
rm -f "/etc/nginx/sites-enabled/$SERVICE-api" "/etc/nginx/sites-available/$SERVICE-api"
rm -f "/etc/nginx/sites-enabled/$SERVICE-client" "/etc/nginx/sites-available/$SERVICE-client"
if command -v nginx &>/dev/null; then
  nginx -t 2>/dev/null && systemctl reload nginx || echo "    (nginx not reloaded -- check config)"
fi

echo "==> removing firewall rules added by install.sh (if ufw is in use)"
UFW_STILL_ACTIVE=false
if command -v ufw &>/dev/null; then
  ufw status 2>/dev/null | grep -q "^Status: active" && UFW_STILL_ACTIVE=true
  if [[ -n "$DOMAIN" || "$CLIENT_MODE" == "subdomain" ]]; then
    if [[ "$PUBLIC_PORT" == "80" ]]; then
      ufw delete allow 'Nginx Full' 2>/dev/null || true
    else
      ufw delete allow "$PUBLIC_PORT"/tcp 2>/dev/null || true
      ufw delete allow 443/tcp 2>/dev/null || true
    fi
  fi
  # Only force-enabled ufw when it was already active at install time; never
  # disable it here — it may protect other services on the box.
  if $UFW_STILL_ACTIVE; then
    if [[ "$UFW_WAS_ACTIVE" == "false" ]]; then
      echo "    NOTE: ufw is active but this install never enabled it."
      echo "    Leave it if you turned it on yourself; otherwise: ufw disable"
    else
      echo "    NOTE: ufw is still active. If another service became unreachable,"
      echo "    check 'ufw status' / 'ufw allow <port>/tcp' rather than rebooting."
    fi
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
  echo "    skipped -- $REPO_DIR left in place"
fi

echo "==> --purge: removing service user '$SERVICE_USER'"
read -r -p "    type YES to confirm: " confirm_user
if [[ "$confirm_user" == "YES" ]]; then
  userdel "$SERVICE_USER" 2>/dev/null || true
else
  echo "    skipped -- user left in place"
fi

echo "==> done"
