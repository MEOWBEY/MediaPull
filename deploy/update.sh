#!/usr/bin/env bash
# Routine "pull latest code and restart" for the backend (and client, if
# install.sh set one up). Run as your own admin/sudo user (NOT the "pullbox"
# service user, which has no login shell):
#   sudo /opt/pullbox/deploy/update.sh
#
# No prompts and no GitHub credentials needed: install.sh persisted the
# authenticated remote into the checkout, so the git pull below just works.
# (A fresh provisioning run is install.sh; this is the fast day-to-day path.)
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

require_root
load_config

# Defaults for anything a very old .vps-deploy.env didn't record.
PORT="${PORT:-8000}"
CLIENT_MODE="${CLIENT_MODE:-none}"
DOMAIN="${DOMAIN:-}"
INSTALL_POT_PROVIDER="${INSTALL_POT_PROVIDER:-no}"
POT_PORT="${POT_PORT:-4416}"

sync_repo

echo "==> installing backend dependencies"
install_backend_deps
scrub_obsolete_env
upgrade_scrapers

if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  echo "==> upgrading the YouTube PO token provider (port $POT_PORT)"
  if sync_pot_provider_code; then
    sync_pot_service "$POT_PORT"
    systemctl restart pullbox-pot
  else
    echo "    PO token provider upgrade skipped (plugin not resolvable this run)." >&2
  fi
fi

build_client "$CLIENT_MODE" "$DOMAIN"

# Reuse the caps install saved; fall back to a fresh detection only for an old
# .vps-deploy.env written before resource limits existed.
detect_resource_limits
echo "==> syncing the systemd unit (MemoryMax=$MEMORY_MAX, CPUQuota=$CPU_QUOTA)"
sync_systemd_unit "$PORT" "$MEMORY_MAX" "$CPU_QUOTA"

restart_and_health "$PORT"
