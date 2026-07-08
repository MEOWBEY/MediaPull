#!/usr/bin/env bash
# Zero-fuss update script for the backend (and client, if install.sh set one
# up) on a VPS. Run as your own admin/sudo user (NOT the "directstream"
# service user, which has no login shell and no sudo rights):
#   sudo /opt/directstream/deploy/server/vps/update.sh
set -euo pipefail

REPO_DIR="${REPO_DIR:-/opt/directstream}"
SERVICE_USER="${SERVICE_USER:-directstream}"
SERVICE="directstream"
PORT="${PORT:-8000}"
CLIENT_MODE="${CLIENT_MODE:-none}"
INSTALL_POT_PROVIDER="${INSTALL_POT_PROVIDER:-no}"
# Falls back to a fresh detection if this update is running against a
# .vps-deploy.env written before resource limits existed (upgrade path).
MEMORY_MAX="${MEMORY_MAX:-}"
CPU_QUOTA="${CPU_QUOTA:-}"
CONFIG_FILE="$REPO_DIR/.vps-deploy.env"

# install.sh writes this with the answers you gave it, so update.sh doesn't
# need REPO_DIR/PORT/etc re-specified every time -- env vars above still win
# if you deliberately want to override one for this run.
if [[ -f "$CONFIG_FILE" ]]; then
  # shellcheck disable=SC1090
  source <(grep -v '^\s*#' "$CONFIG_FILE")
fi

cd "$REPO_DIR"

branch="$(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)"
if [[ "$branch" == "HEAD" ]]; then
  echo "==> this checkout is in a detached HEAD state (probably from a previous" >&2
  echo "    rollback -- see the README's 'If an update breaks something' section)." >&2
  echo "    Check out a real branch first, e.g.:" >&2
  echo "      cd $REPO_DIR && sudo -u $SERVICE_USER git checkout main" >&2
  exit 1
fi

echo "==> current commit: $(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --short HEAD)"
sudo -u "$SERVICE_USER" git -C "$REPO_DIR" fetch origin
sudo -u "$SERVICE_USER" git -C "$REPO_DIR" pull --ff-only origin "$branch"
echo "==> new commit:     $(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --short HEAD)"

echo "==> installing backend dependencies"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install -r "$REPO_DIR/server/requirements.txt"

# yt-dlp and gallery-dl fight a constant arms race against site changes
# (YouTube/Instagram/X break scrapers often) -- the exact version pinned in
# requirements.txt only moves when someone edits the app's code, which can
# lag real fixes upstream by weeks. Always pull the latest release of both on
# every update, on top of (not instead of) the pinned requirements above, so
# "the extractor doesn't support this site anymore" gets fixed by an update
# even between app releases.
echo "==> upgrading yt-dlp and gallery-dl to their latest releases"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade yt-dlp gallery-dl

# The PO token provider's Python plugin and its Node.js server speak a
# version-checked protocol -- both must move together, or yt-dlp's plugin
# starts rejecting a now-mismatched server. Only touches anything if
# install.sh set this up in the first place.
if [[ "$INSTALL_POT_PROVIDER" == "yes" ]]; then
  echo "==> upgrading the YouTube PO token provider"
  sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade bgutil-ytdlp-pot-provider
  POT_VERSION="$(sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" show bgutil-ytdlp-pot-provider 2>/dev/null | sed -n 's/^Version: //p')"
  POT_DIR="$REPO_DIR/pot-provider"
  if [[ -n "$POT_VERSION" && -d "$POT_DIR/.git" ]]; then
    CURRENT_POT_TAG="$(sudo -u "$SERVICE_USER" git -C "$POT_DIR" describe --tags --exact-match 2>/dev/null || echo "")"
    if [[ "$CURRENT_POT_TAG" != "$POT_VERSION" ]]; then
      sudo -u "$SERVICE_USER" git -C "$POT_DIR" fetch --tags origin
      sudo -u "$SERVICE_USER" git -C "$POT_DIR" checkout "$POT_VERSION"
      sudo -u "$SERVICE_USER" bash -c "cd '$POT_DIR/server' && npm ci && npx tsc"
    fi
    systemctl restart directstream-pot
  fi
fi

if [[ "$CLIENT_MODE" != "none" ]]; then
  echo "==> rebuilding the client ($CLIENT_MODE)"
  if [[ "$CLIENT_MODE" == "subdomain" ]]; then
    sudo -u "$SERVICE_USER" bash -c \
      "cd '$REPO_DIR/client' && VITE_API_BASE_URL='https://${DOMAIN:-}' npm ci && npm run build"
  else
    sudo -u "$SERVICE_USER" bash -c "cd '$REPO_DIR/client' && npm ci && npm run build"
  fi
fi

if [[ -z "$MEMORY_MAX" || -z "$CPU_QUOTA" ]]; then
  CORES="$(nproc 2>/dev/null || echo 1)"
  MEM_TOTAL_MB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1024 ))
  MEMORY_MAX="${MEMORY_MAX:-$(( MEM_TOTAL_MB * 70 / 100 ))M}"
  QUOTA_CORES=$(( CORES - 1 )); [[ "$QUOTA_CORES" -lt 1 ]] && QUOTA_CORES=1
  CPU_QUOTA="${CPU_QUOTA:-$(( QUOTA_CORES * 100 ))%}"
fi

echo "==> syncing the systemd unit (picks up template fixes a restart alone would miss)"
sed "s/__PORT__/$PORT/; s/__MEMORY_MAX__/$MEMORY_MAX/; s/__CPU_QUOTA__/$CPU_QUOTA/" \
  "$REPO_DIR/deploy/server/vps/directstream.service" \
  > /etc/systemd/system/directstream.service
systemctl daemon-reload

echo "==> restarting service"
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager status "$SERVICE"

echo "==> health check"
curl -fsS "http://127.0.0.1:$PORT/health" && echo " OK"
