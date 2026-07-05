#!/usr/bin/env bash
# Zero-fuss update script for the backend service on a VPS.
# Run as your own admin/sudo user (NOT the "directstream" service user,
# which has no login shell and no sudo rights):
#   sudo /opt/directstream/deploy/server/vps/update.sh
set -euo pipefail

REPO_DIR="/opt/directstream"
SERVICE_USER="directstream"
SERVICE="directstream"

cd "$REPO_DIR"

echo "==> current commit: $(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --short HEAD)"
sudo -u "$SERVICE_USER" git -C "$REPO_DIR" fetch origin
sudo -u "$SERVICE_USER" git -C "$REPO_DIR" pull --ff-only origin \
    "$(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)"
echo "==> new commit:     $(sudo -u "$SERVICE_USER" git -C "$REPO_DIR" rev-parse --short HEAD)"

echo "==> installing backend dependencies"
sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install -r "$REPO_DIR/server/requirements.txt"

echo "==> restarting service"
systemctl restart "$SERVICE"
sleep 2
systemctl --no-pager status "$SERVICE"

echo "==> health check"
curl -fsS http://127.0.0.1:8000/health && echo " OK"
