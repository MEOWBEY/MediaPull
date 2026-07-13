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

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# Uninstall-specific settings (REPO_DIR/SERVICE_USER/SERVICE/CONFIG_FILE come
# from lib.sh). Defaults here are overridden by whatever install.sh recorded.
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
systemctl stop pullbox-pot 2>/dev/null || true
systemctl disable pullbox-pot 2>/dev/null || true
rm -f /etc/systemd/system/pullbox-pot.service

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
  # install.sh only force-enables ufw when it was ALREADY active beforehand
  # (see its comment) -- so if we know it wasn't, Pullbox never turned the
  # firewall on and there's nothing to revert. If we don't know (older
  # install, no UFW_WAS_ACTIVE recorded) or it WAS already active, leave ufw
  # as-is -- it may be protecting other things on this box now, disabling it
  # here could be more surprising than helpful. Just tell you the truth
  # about its current state instead of leaving you to guess (or reboot).
  if $UFW_STILL_ACTIVE; then
    if [[ "$UFW_WAS_ACTIVE" == "false" ]]; then
      echo "    NOTE: ufw is active but this install never turned it on -- if you enabled"
      echo "    it yourself since, leave it; otherwise 'ufw disable' removes it entirely."
    else
      echo "    NOTE: ufw is still active. If anything else on this box (a control panel,"
      echo "    another service) stopped being reachable after installing/removing"
      echo "    Pullbox, it's very likely ufw blocking that port, not a crash --"
      echo "    check 'ufw status' and 'ufw allow <port>/tcp' rather than rebooting."
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
