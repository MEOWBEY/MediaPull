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

if [[ "$CLIENT_MODE" != "none" ]]; then
  echo "==> rebuilding the client ($CLIENT_MODE)"
  if [[ "$CLIENT_MODE" == "subdomain" ]]; then
    sudo -u "$SERVICE_USER" bash -c \
      "cd '$REPO_DIR/client' && VITE_API_BASE_URL='https://${DOMAIN:-}' npm ci && npm run build"
  else
    sudo -u "$SERVICE_USER" bash -c "cd '$REPO_DIR/client' && npm ci && npm run build"
  fi
fi

echo "==> restarting service"
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager status "$SERVICE"

echo "==> health check"
curl -fsS "http://127.0.0.1:$PORT/health" && echo " OK"
