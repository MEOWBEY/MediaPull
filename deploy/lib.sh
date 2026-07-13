#!/usr/bin/env bash
# Shared helpers for the Pullbox VPS scripts (install/update/uninstall).
#
# SOURCED, never executed on its own -- each entry script does:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
# and inherits the constants + functions below. The sourcing script owns
# `set -euo pipefail`; this file only defines things.
#
# Everything here is the code install.sh and update.sh would otherwise
# duplicate (git sync, dependency installs, yt-dlp / PO-token upgrades, client
# build, systemd templating, health check) plus the token-based git auth that
# stops a private repo from re-prompting for credentials on every clone/pull.

# ---- constants / defaults (override by exporting the var before sourcing) ---
REPO_SLUG="${REPO_SLUG:-MEOWBEY/direct-stream}"
REPO_URL="${REPO_URL:-https://github.com/${REPO_SLUG}.git}"
REPO_DIR="${REPO_DIR:-/opt/pullbox}"
SERVICE_USER="${SERVICE_USER:-pullbox}"
SERVICE="pullbox"
CONFIG_FILE="$REPO_DIR/.vps-deploy.env"

# Directory (inside the checkout) holding the deploy templates this lib fills
# in -- systemd units, nginx/caddy configs. Set relative to this file so the
# scripts keep working no matter where the repo is cloned.
DEPLOY_DIR="${DEPLOY_DIR:-$REPO_DIR/deploy}"

# Settings retired from the app in past releases -- scrubbed from a long-lived
# server/.env so nobody wastes time tuning a knob that no longer exists (the
# app ignores unknown keys, so this is hygiene). Add to this list when a
# setting is removed; both install.sh (re-run) and update.sh use it.
OBSOLETE_ENV_KEYS=(
  TRANSCRIBE_CHUNK_SECONDS
  GROQ_CHUNK_CONCURRENCY
)

# ---- misc guards -----------------------------------------------------------
require_root() {
  if [[ $EUID -ne 0 ]]; then
    echo "Run as root (or with sudo)." >&2
    exit 1
  fi
}

# install.sh writes CONFIG_FILE with the answers you gave it, so update.sh /
# uninstall.sh don't need REPO_DIR/PORT/etc re-specified. Env vars set before
# the run still win (they were already set when the defaults above resolved).
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

# True if origin already carries an embedded credential -- lets install.sh skip
# re-asking for a token on a re-run, and confirms update.sh will never prompt.
remote_has_auth() {
  git_c remote get-url origin 2>/dev/null | grep -q '@github.com'
}

# Persist the authenticated remote into the checkout's (service-user-owned)
# .git/config, so every later git op -- including update.sh -- reuses it with
# no prompt. No-op for a blank token.
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

# yt-dlp / gallery-dl fight a constant arms race with site changes, so always
# pull their latest release on top of (not instead of) the pinned versions.
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

# YouTube PO token provider: pip plugin + a pinned Node server clone that speak
# a version-checked protocol, so both must move together. Ensures the clone is
# at the tag pip resolved and (re)builds it. Sets POT_VERSION for the caller;
# returns non-zero if the plugin didn't install. Does NOT create the systemd
# service (install.sh does that once).
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

# (Re)template the PO provider systemd unit for the given port (default 4416)
# and reload systemd. Shared by install.sh (first setup) and update.sh (so a
# template/port change propagates on the next update).
sync_pot_service() {
  local port="${1:-4416}"
  sed "s#__REPO_DIR__#$REPO_DIR#; s#__SERVICE_USER__#$SERVICE_USER#; s#__POT_PORT__#$port#" \
    "$DEPLOY_DIR/systemd/pullbox-pot.service" \
    > /etc/systemd/system/pullbox-pot.service
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
    "$DEPLOY_DIR/systemd/pullbox.service" \
    > /etc/systemd/system/pullbox.service
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
