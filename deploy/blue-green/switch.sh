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
# - State is stored in deploy/blue-green/.active-slot (gitignored), default "blue".
# - Only the nginx proxy publishes a host port (default 9000, override with BLUE_GREEN_PORT).
# - Images are public on ghcr.io — no docker login needed.
set -euo pipefail

# Resolve script and compose locations so the script works from any cwd.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
ACTIVE_FILE="$SCRIPT_DIR/.active-slot"
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
  POSTGRES_PASSWORD     Required for "deploy" (must be set, same as compose up)
  BLUE_TAG / GREEN_TAG  Override image tags for the respective slot (used by deploy)

Examples:
  POSTGRES_PASSWORD=secret ./switch.sh status
  ./switch.sh switch green
  POSTGRES_PASSWORD=secret ./switch.sh deploy 0.1.0
  ./switch.sh rollback
EOF
}

# Read active slot from file, default to blue. Validates content.
get_active() {
  if [ -f "$ACTIVE_FILE" ]; then
    # Trim whitespace/newlines, take first word
    local val
    val="$(tr -d ' \t\r\n' < "$ACTIVE_FILE" 2>/dev/null || echo "blue")"
    case "$val" in
      blue|green) echo "$val" ;;
      *) echo "blue" ;;
    esac
  else
    echo "blue"
  fi
}

# Persist active slot (atomic via printf)
set_active() {
  local slot="$1"
  printf "%s\n" "$slot" > "$ACTIVE_FILE"
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
  # Show file location for teaching
  if [ -f "$ACTIVE_FILE" ]; then
    printf "State file: %s\n" "$ACTIVE_FILE"
  else
    printf "State file: (default, %s not yet created)\n" "$ACTIVE_FILE"
  fi
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
  docker compose -f "$COMPOSE_FILE" exec -T proxy sh -c "ACTIVE_SLOT=$target envsubst '\${ACTIVE_SLOT}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/conf.d/default.conf && nginx -s reload"

  # Persist new active slot
  set_active "$target"

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

# Deploy a tag to the inactive slot, wait healthy, then switch
do_deploy() {
  local tag="$1"
  if [ -z "$tag" ]; then
    printf "Error: deploy requires a tag argument\n" >&2
    usage
    exit 1
  fi

  local current inactive
  current="$(get_active)"
  if [ "$current" = "blue" ]; then
    inactive="green"
  else
    inactive="blue"
  fi

  printf "Deploying tag %s to inactive slot %s (current %s)...\n" "$tag" "$inactive" "$current"

  # Ensure POSTGRES_PASSWORD is set (compose requires it)
  if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    printf "Error: POSTGRES_PASSWORD must be set for deploy (same as compose up)\n" >&2
    printf "  POSTGRES_PASSWORD=... %s deploy %s\n" "$0" "$tag" >&2
    exit 1
  fi

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

  # Final smoke-test: version should match deployed tag
  if command -v curl >/dev/null 2>&1; then
    printf "Verifying version via proxy...\n"
    local ver
    ver="$(curl --fail --silent --show-error --max-time 5 "http://localhost:${PORT}/version" 2>/dev/null || echo "")"
    printf "Proxy /version: %s\n" "$ver"
    if command -v jq >/dev/null 2>&1 && [ -n "$ver" ]; then
      # Check .version == tag (jq returns 0 if true)
      if echo "$ver" | jq --exit-status --arg expected "$tag" '.version == $expected' >/dev/null 2>&1; then
        printf "Version check passed: %s\n" "$tag"
      else
        printf "Warning: version mismatch (expected %s)\n" "$tag" >&2
      fi
    fi
  fi
}

# Rollback is switching to the opposite slot (the one not currently active)
do_rollback() {
  local current inactive
  current="$(get_active)"
  if [ "$current" = "blue" ]; then
    inactive="green"
  else
    inactive="blue"
  fi
  printf "Rollback: switching from %s to %s\n" "$current" "$inactive"
  do_switch "$inactive"
}

# Main dispatch
if [ $# -eq 0 ]; then
  usage
  exit 1
fi

cmd="$1"
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
