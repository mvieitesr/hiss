#!/usr/bin/env bash
# Hiss — blue-green switch script (teaching demo)
# Usage:
#   ./switch.sh status              # show active slot
#   ./switch.sh switch blue|green   # cut over to that slot (also: ./switch.sh blue|green)
#   ./switch.sh deploy <tag>        # deploy <tag> to inactive slot, wait healthy, switch
#   ./switch.sh rollback            # switch back to the other slot
#
# Notes:
# - Compatible with bash 3.2 (macOS) and bash 5 (Linux). No readarray, no GNU-only sed.
# - The proxy's project-scoped volume persists the selected slot (default "blue").
# - Only the nginx proxy publishes a host port (default 9000, override with BLUE_GREEN_PORT).
# - Images are public on ghcr.io — no docker login needed.
set -euo pipefail

# Resolve script and compose locations so the script works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
# Host port for smoke tests; matches ${BLUE_GREEN_PORT:-9000} in compose.yml
PORT="${BLUE_GREEN_PORT:-9000}"

# ANSI colors (only if stdout is a tty)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  BLUE='\033[0;34m'
  YELLOW='\033[0;33m'
  RESET='\033[0m'
else
  GREEN=''
  BLUE=''
  YELLOW=''
  RESET=''
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") <command> [args]

Commands:
  status                Show active slot (blue or green)
  switch <blue|green>   Switch traffic to that slot (idempotent)
  deploy <tag>          Deploy <tag> to the inactive slot, wait healthy, then switch
  rollback              Switch back to the other slot (alias for switching to inactive)

Shorthand:
  $(basename "$0") blue|green   Same as "switch blue|green"

Environment:
  BLUE_GREEN_PORT       Host port for proxy (default 9000)
  POSTGRES_PASSWORD     Required for all operations (same as compose up)
  BLUE_TAG / GREEN_TAG  Override image tags for the respective slot (used by deploy)

Examples:
  POSTGRES_PASSWORD=secret ./switch.sh status
  ./switch.sh switch green
  POSTGRES_PASSWORD=secret ./switch.sh deploy 0.1.0
  ./switch.sh rollback
EOF
}

# Read the actual proxy configuration, not the persisted startup preference.
get_active() {
  local slot
  if ! slot="$(docker compose -f "$COMPOSE_FILE" exec -T proxy awk '
    $1 == "proxy_pass" && $2 == "http://blue:8000;" { print "blue" }
    $1 == "proxy_pass" && $2 == "http://green:8000;" { print "green" }
  ' /etc/nginx/conf.d/default.conf)"; then
    printf "Error: cannot read the running proxy; start the demo first.\n" >&2
    return 1
  fi
  case "$slot" in
    blue|green) printf '%s\n' "$slot" ;;
    *) printf "Error: proxy configuration has no unique active slot.\n" >&2; return 1 ;;
  esac
}

# Print status with color and extra context
do_status() {
  local active
  active="$(get_active)"
  if [ "$active" = "blue" ]; then
    printf "Active slot: ${BLUE}blue${RESET} (port %s -> blue:8000)\n" "$PORT"
  else
    printf "Active slot: ${GREEN}green${RESET} (port %s -> green:8000)\n" "$PORT"
  fi
  printf "Startup state: project-scoped proxy-state volume\n"
  # Optional: show running containers if docker is available
  if command -v docker >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" ps 2>/dev/null || true
  fi
}

# Wait for a slot to become healthy (polling docker inspect). Timeout in seconds.
wait_healthy() {
  local slot="$1"
  local timeout="${2:-60}"
  local elapsed=0
  printf "Waiting for %s to become healthy (timeout %ss)...\n" "$slot" "$timeout"
  while [ "$elapsed" -lt "$timeout" ]; do
    local cid
    # Get container id for the slot service; empty if not yet created
    cid="$(docker compose -f "$COMPOSE_FILE" ps -q "$slot" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      local status
      # Health status is "healthy", "starting", "unhealthy", or empty if no healthcheck
      status="$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "unknown")"
      if [ "$status" = "healthy" ]; then
        printf "%s is healthy\n" "$slot"
        return 0
      fi
      printf "  %s status: %s (%ss elapsed)\n" "$slot" "$status" "$elapsed"
    else
      printf "  %s container not yet created (%ss elapsed)\n" "$slot" "$elapsed"
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  printf "Timeout: %s did not become healthy within %ss\n" "$slot" "$timeout" >&2
  return 1
}

# Perform the actual nginx switch (render template inside proxy and reload)
do_switch() {
  local target="$1"
  # Validate target
  case "$target" in
    blue|green) ;;
    *) printf "Error: target must be blue or green, got '%s'\n" "$target" >&2; usage; exit 1 ;;
  esac

  local current
  current="$(get_active)"
  if [ "$current" = "$target" ]; then
    printf "Already on ${YELLOW}%s${RESET} — no change (idempotent)\n" "$target"
    return 0
  fi

  printf "Switching from %s to %s...\n" "$current" "$target"

  # Render the nginx config inside the proxy container and reload.
  # Uses explicit envsubst '${ACTIVE_SLOT}' so only that var is substituted;
  # $host, $remote_addr etc. are preserved.
  # The proxy container must be running; if not, give a helpful error.
  if ! docker compose -f "$COMPOSE_FILE" ps --status running 2>/dev/null | grep -q "proxy"; then
    printf "Error: proxy container is not running. Start the demo first:\n" >&2
    printf "  POSTGRES_PASSWORD=... docker compose -f %s up -d\n" "$COMPOSE_FILE" >&2
    exit 1
  fi

  # Exec inside proxy: set ACTIVE_SLOT for this command, render, reload
  # Note: the single quotes around \${ACTIVE_SLOT} are for the container's shell;
  # we escape $ for compose (via $$ in compose.yml) but here we are inside
  # the container's shell directly, so we use standard '${ACTIVE_SLOT}'.
  docker compose -f "$COMPOSE_FILE" exec -T proxy sh -c "ACTIVE_SLOT=$target envsubst '\${ACTIVE_SLOT}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -s reload && printf '%s\\n' '$target' > /var/lib/hiss-blue-green/active-slot"

  # Confirmation with color
  if [ "$target" = "blue" ]; then
    printf "Switched to ${BLUE}blue${RESET}\n"
  else
    printf "Switched to ${GREEN}green${RESET}\n"
  fi

  # Brief pause then smoke-test the proxy (best effort, don't fail switch if curl fails)
  sleep 1
  if command -v curl >/dev/null 2>&1; then
    printf "Smoke check: curl http://localhost:%s/version\n" "$PORT"
    curl --fail --silent --show-error --max-time 5 "http://localhost:${PORT}/version" 2>&1 | head -n 5 || printf "Warning: proxy not yet reachable (may need a moment)\n" >&2
  fi
}

# Verify that the proxy serves the expected non-empty version.
verify_version() {
  local expected="$1" ver
  printf "Verifying version via proxy...\n"
  if ! ver="$(curl --fail --silent --show-error --max-time 5 "http://localhost:${PORT}/version")"; then
    printf "Error: cannot read proxy version\n" >&2
    return 1
  fi
  printf "Proxy /version: %s\n" "$ver"
  if ! printf '%s\n' "$ver" | jq --exit-status --arg expected "$expected" '.version == $expected and (.version | type == "string" and length > 0)' >/dev/null 2>&1; then
    printf "Error: version mismatch or empty (expected %s)\n" "$expected" >&2
    return 1
  fi
  printf "Version check passed: %s\n" "$expected"
}

# Deploy a tag to the inactive slot, wait healthy, then switch
do_deploy() {
  local tag="$1"
  if [ -z "$tag" ]; then
    printf "Error: deploy requires a tag argument\n" >&2
    usage
    exit 1
  fi
  if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
    printf "Error: deploy requires curl and jq to verify the version\n" >&2
    return 1
  fi

  local current inactive
  current="$(get_active)"
  if [ "$current" = "blue" ]; then
    inactive="green"
  else
    inactive="blue"
  fi

  printf "Deploying tag %s to inactive slot %s (current %s)...\n" "$tag" "$inactive" "$current"

  # Pull and up the inactive slot with the new tag.
  # We set the slot-specific tag env var for this compose invocation only.
  # Use --pull never for local validation (images may be local-only in tests);
  # fallback to normal pull if the image is remote and public.
  if [ "$inactive" = "blue" ]; then
    # shellcheck disable=SC2090
    MIGRATE_TAG="$tag" BLUE_TAG="$tag" docker compose -f "$COMPOSE_FILE" up -d --pull never "$inactive" || MIGRATE_TAG="$tag" BLUE_TAG="$tag" docker compose -f "$COMPOSE_FILE" up -d "$inactive"
  else
    MIGRATE_TAG="$tag" GREEN_TAG="$tag" docker compose -f "$COMPOSE_FILE" up -d --pull never "$inactive" || MIGRATE_TAG="$tag" GREEN_TAG="$tag" docker compose -f "$COMPOSE_FILE" up -d "$inactive"
  fi

  # Wait for the newly deployed slot to be healthy
  if ! wait_healthy "$inactive" 60; then
    printf "Error: %s failed to become healthy — not switching. Check logs:\n" "$inactive" >&2
    printf "  docker compose -f %s logs %s\n" "$COMPOSE_FILE" "$inactive" >&2
    exit 1
  fi

  # Switch traffic to the newly deployed slot
  do_switch "$inactive"

  verify_version "$tag"
}

# Rollback is switching to the opposite slot (the one not currently active)
do_rollback() {
  if ! command -v curl >/dev/null 2>&1 || ! command -v jq >/dev/null 2>&1; then
    printf "Error: rollback requires curl and jq to verify the version\n" >&2
    return 1
  fi
  local current inactive expected
  current="$(get_active)"
  if [ "$current" = "blue" ]; then
    inactive="green"
  else
    inactive="blue"
  fi
  if ! expected="$(docker compose -f "$COMPOSE_FILE" exec -T "$inactive" python -c \
    'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/version", timeout=5).read().decode())' |
    jq -er '.version | select(type == "string" and length > 0)')"; then
    printf "Error: cannot read the rollback slot version\n" >&2
    return 1
  fi
  printf "Rollback: switching from %s to %s\n" "$current" "$inactive"
  do_switch "$inactive"
  verify_version "$expected"
}

# Main dispatch
if [ $# -eq 0 ]; then
  usage
  exit 1
fi

cmd="$1"
if [ "$cmd" != "help" ] && [ "$cmd" != "--help" ] && [ "$cmd" != "-h" ] && [ -z "${POSTGRES_PASSWORD:-}" ]; then
  printf "Error: POSTGRES_PASSWORD must be set (use the same value as compose up).\n" >&2
  exit 1
fi
# Support shorthand: ./switch.sh blue|green
if [ "$cmd" = "blue" ] || [ "$cmd" = "green" ]; then
  do_switch "$cmd"
  exit 0
fi

case "$cmd" in
  status)
    do_status
    ;;
  switch)
    if [ $# -ne 2 ]; then
      printf "Error: switch requires an argument (blue|green)\n" >&2
      usage
      exit 1
    fi
    do_switch "$2"
    ;;
  deploy)
    if [ $# -ne 2 ]; then
      printf "Error: deploy requires a tag argument\n" >&2
      usage
      exit 1
    fi
    do_deploy "$2"
    ;;
  rollback)
    do_rollback
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    printf "Error: unknown command '%s'\n" "$cmd" >&2
    usage
    exit 1
    ;;
esac
