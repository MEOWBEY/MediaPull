#!/usr/bin/env bash
# Shared helpers for MediaPull VPS scripts (install/update/uninstall).
# Sourced only — not executed on its own. Caller owns set -euo pipefail.

# ---- constants / defaults (override by exporting before sourcing) -----------
REPO_SLUG="${REPO_SLUG:-meowbey/MediaPull}"
REPO_URL="${REPO_URL:-https://github.com/${REPO_SLUG}.git}"
REPO_DIR="${REPO_DIR:-/opt/mediapull}"
SERVICE_USER="${SERVICE_USER:-mediapull}"
SERVICE="mediapull"
CONFIG_FILE="$REPO_DIR/.vps-deploy.env"
# Templates live next to this file so scripts work from any checkout path.
DEPLOY_DIR="${DEPLOY_DIR:-$REPO_DIR/deploy}"

# Keys removed from the app — scrubbed from long-lived server/.env on update.
OBSOLETE_ENV_KEYS=(
  TRANSCRIBE_CHUNK_SECONDS
  GROQ_CHUNK_CONCURRENCY
  YOUTUBE_PO_TOKEN
)

# ---- misc guards -----------------------------------------------------------
require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Run as root (or with sudo)." >&2
    exit 1
  fi
}

# Prefer CONFIG_FILE from install.sh; pre-set env vars still win.
load_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    # shellcheck disable=SC1090
    source <(grep -v '^[[:space:]]*#' "$CONFIG_FILE")
  fi
}

# ---- git (auth that never re-prompts) --------------------------------------
# Run git as the service user inside the checkout. GIT_TERMINAL_PROMPT=0 makes
# a missing/invalid credential FAIL FAST with a clear error instead of hanging
# on (or repeatedly re-showing) an interactive username/password prompt -- the
# "it asks 3 times for GitHub auth" symptom.
git_c() {
  sudo -u "$SERVICE_USER" GIT_TERMINAL_PROMPT=0 git -C "$REPO_DIR" "$@"
}

# Fold a token into an https://github.com URL so clone/fetch/pull authenticate
# non-interactively. A blank token (public repo) returns the URL unchanged.
authed_url() {
  local url="$1" token="${2:-}"
  if [[ -n "$token" && "$url" == https://github.com/* ]]; then
    printf 'https://%s@github.com/%s' "$token" "${url#https://github.com/}"
  else
    printf '%s' "$url"
  fi
}

# True if origin URL already embeds credentials (skip re-prompting).
remote_has_auth() {
  git_c remote get-url origin 2>/dev/null | grep -q '@github.com'
}

# Write authenticated remote into the service user's .git/config. No-op if blank.
persist_repo_auth() {
  local token="${1:-}"
  [[ -n "$token" ]] || return 0
  git_c remote set-url origin "$(authed_url "$REPO_URL" "$token")"
}

current_branch() {
  git_c rev-parse --abbrev-ref HEAD 2>/dev/null || echo "HEAD"
}

# fetch + fast-forward pull the current branch. Returns non-zero (without
# aborting a `set -e` caller that checks it) on a detached HEAD so the caller
# can print its own guidance.
sync_repo() {
  local branch
  branch="$(current_branch)"
  if [[ "$branch" == "HEAD" ]]; then
    echo "    $REPO_DIR is in a detached HEAD state -- check out a branch first:" >&2
    echo "      cd $REPO_DIR && sudo -u $SERVICE_USER git checkout main" >&2
    return 1
  fi
  echo "==> current commit: $(git_c rev-parse --short HEAD)"
  git_c fetch origin
  git_c pull --ff-only origin "$branch"
  echo "==> new commit:     $(git_c rev-parse --short HEAD)"
}

# ---- dependencies ----------------------------------------------------------
install_backend_deps() {
  sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install \
    -r "$REPO_DIR/server/requirements.txt"
}

# Always upgrade scrapers on top of pinned requirements (sites change often).
upgrade_scrapers() {
  echo "==> upgrading yt-dlp and gallery-dl to their latest releases"
  sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade yt-dlp gallery-dl
}

scrub_obsolete_env() {
  local env_file="$REPO_DIR/server/.env" key
  [[ -f "$env_file" ]] || return 0
  for key in "${OBSOLETE_ENV_KEYS[@]}"; do
    if grep -q "^${key}=" "$env_file"; then
      echo "==> removing obsolete setting $key from server/.env"
      sudo -u "$SERVICE_USER" sed -i "/^${key}=/d" "$env_file"
    fi
  done
}

# Keep bgutil pot plugin + Node server on the same version-checked tag.
# Sets POT_VERSION; does not create the systemd unit (install.sh does).
sync_pot_provider_code() {
  sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" install --upgrade bgutil-ytdlp-pot-provider
  POT_VERSION="$(sudo -u "$SERVICE_USER" "$REPO_DIR/server/venv/bin/pip" show bgutil-ytdlp-pot-provider 2>/dev/null | sed -n 's/^Version: //p')"
  [[ -n "$POT_VERSION" ]] || return 1
  local dir="$REPO_DIR/pot-provider" tag
  if [[ -d "$dir/.git" ]]; then
    tag="$(sudo -u "$SERVICE_USER" git -C "$dir" describe --tags --exact-match 2>/dev/null || echo "")"
    if [[ "$tag" != "$POT_VERSION" ]]; then
      sudo -u "$SERVICE_USER" git -C "$dir" fetch --tags origin
      sudo -u "$SERVICE_USER" git -C "$dir" checkout "$POT_VERSION"
      sudo -u "$SERVICE_USER" bash -c "cd '$dir/server' && npm ci && npx tsc"
    fi
  else
    sudo -u "$SERVICE_USER" git clone --single-branch --branch "$POT_VERSION" \
      https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git "$dir"
    sudo -u "$SERVICE_USER" bash -c "cd '$dir/server' && npm ci && npx tsc"
  fi
}

# Template mediapull-pot.service for the given port (default 4416) and reload.
sync_pot_service() {
  local port="${1:-4416}"
  sed "s#__REPO_DIR__#$REPO_DIR#; s#__SERVICE_USER__#$SERVICE_USER#; s#__POT_PORT__#$port#" \
    "$DEPLOY_DIR/systemd/mediapull-pot.service" \
    > /etc/systemd/system/mediapull-pot.service
  systemctl daemon-reload
}

# ---- client build ----------------------------------------------------------
build_client() {
  local mode="$1" domain="${2:-}"
  case "$mode" in
    same-domain)
      echo "==> building the client (same-origin)"
      sudo -u "$SERVICE_USER" bash -c "cd '$REPO_DIR/client' && npm ci && npm run build"
      ;;
    subdomain)
      echo "==> building the client (subdomain; API https://$domain)"
      sudo -u "$SERVICE_USER" bash -c \
        "cd '$REPO_DIR/client' && VITE_API_BASE_URL='https://$domain' npm ci && npm run build"
      ;;
    *) : ;;  # "none" / anything else -- nothing to build
  esac
}

# ---- systemd / resource limits / health ------------------------------------
# Fills MEMORY_MAX / CPU_QUOTA if unset (a fresh install computes them; update
# reuses what install saved). Also exports CPU_CORES / MEM_TOTAL_MB for callers
# that want to print or branch on box size.
detect_resource_limits() {
  CPU_CORES="$(nproc 2>/dev/null || echo 1)"
  MEM_TOTAL_MB=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1024 ))
  if [[ -z "${MEMORY_MAX:-}" ]]; then
    local mm=$(( MEM_TOTAL_MB * 70 / 100 ))
    [[ "$mm" -lt 1 ]] && mm=256
    MEMORY_MAX="${mm}M"
  fi
  if [[ -z "${CPU_QUOTA:-}" ]]; then
    local qc=$(( CPU_CORES - 1 ))
    [[ "$qc" -lt 1 ]] && qc=1
    CPU_QUOTA="$(( qc * 100 ))%"
  fi
}

sync_systemd_unit() {
  local port="$1" mem="$2" cpu="$3"
  sed "s#__REPO_DIR__#$REPO_DIR#; s#__SERVICE_USER__#$SERVICE_USER#; s/__PORT__/$port/; s/__MEMORY_MAX__/$mem/; s/__CPU_QUOTA__/$cpu/" \
    "$DEPLOY_DIR/systemd/mediapull.service" \
    > /etc/systemd/system/mediapull.service
  systemctl daemon-reload
}

restart_and_health() {
  local port="$1"
  echo "==> restarting service"
  systemctl restart "$SERVICE"
  sleep 2
  systemctl --no-pager status "$SERVICE" || true
  echo "==> health check"
  if curl -fsS "http://127.0.0.1:$port/health"; then
    echo " OK"
  else
    echo " backend did NOT respond on 127.0.0.1:$port -- check: journalctl -u $SERVICE -n 50"
  fi
}
