#!/usr/bin/env bash
# Hiss — blue-green demo check (manual, not wired into CI)
# Verifies the cutover is observable via /version through the proxy.
# This is the test described in issue #6: the observed version change is the test.
# Not executed in CI — students run it by hand.
#
# Usage:
#   POSTGRES_PASSWORD=secret ./deploy/blue-green/demo-check.sh
#   BLUE_GREEN_PORT=9001 POSTGRES_PASSWORD=secret ./deploy/blue-green/demo-check.sh
#
# Requirements: Docker Compose v2, curl, jq
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/compose.yml"
SWITCH_SH="$SCRIPT_DIR/switch.sh"
PORT="${BLUE_GREEN_PORT:-9000}"
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
  printf "Error: POSTGRES_PASSWORD must be set (use the same value as compose up).\n" >&2
  exit 1
fi

# Colors if tty
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  BLUE='\033[0;34m'
  RESET='\033[0m'
else
  GREEN=''
  BLUE=''
  RESET=''
fi

# Helper: wait for a service to be healthy (poll docker inspect), timeout 60s
wait_healthy() {
  local svc="$1"
  local timeout=60
  local elapsed=0
  printf "Waiting for %s to be healthy (timeout %ss)...\n" "$svc" "$timeout"
  while [ "$elapsed" -lt "$timeout" ]; do
    local cid
    cid="$(docker compose -f "$COMPOSE_FILE" ps -q "$svc" 2>/dev/null || true)"
    if [ -n "$cid" ]; then
      local status
      status="$(docker inspect --format '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo "unknown")"
      if [ "$status" = "healthy" ]; then
        printf "%s is healthy\n" "$svc"
        return 0
      fi
      if [ "$status" = "unhealthy" ]; then
        printf "Error: %s is unhealthy\n" "$svc" >&2
        return 1
      fi
      printf "  %s: %s (%ss)\n" "$svc" "$status" "$elapsed"
    else
      printf "  %s: not yet created (%ss)\n" "$svc" "$elapsed"
    fi
    sleep 2
    elapsed=$((elapsed+2))
  done
  printf "Timeout waiting for %s\n" "$svc" >&2
  return 1
}

printf "=== Blue-green demo check ===\n"
printf "Compose: %s\n" "$COMPOSE_FILE"
printf "Proxy port: %s (override with BLUE_GREEN_PORT)\n" "$PORT"
printf "Project: %s (isolated from hiss-dev/staging/prod on 8001-8003)\n" "${COMPOSE_PROJECT_NAME:-hiss-blue-green}"
printf "Images: %s\n\n" "${IMAGE:-ghcr.io/mvieitesr/hiss}"

# 1. Verify the existing deployment without recreating either slot.
printf "1) Checking the running demo...\n"
wait_healthy "blue" || { docker compose -f "$COMPOSE_FILE" logs blue; exit 1; }
wait_healthy "green" || { docker compose -f "$COMPOSE_FILE" logs green; exit 1; }
wait_healthy "proxy" || { docker compose -f "$COMPOSE_FILE" logs proxy; exit 1; }

printf "Waiting for proxy to be reachable on :%s ...\n" "$PORT"
# Use host-side curl with retries (bounded)
curl --fail --silent --show-error --max-time 5 --retry 10 --retry-delay 2 --retry-connrefused "http://localhost:${PORT}/healthz" >/dev/null
curl --fail --silent --show-error --max-time 5 --retry 10 --retry-delay 2 --retry-connrefused "http://localhost:${PORT}/version" | jq .

# Read each slot directly, so the proxy's answer can be checked against its target.
slot_version() {
  docker compose -f "$COMPOSE_FILE" exec -T "$1" python -c \
    'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8000/version", timeout=5).read().decode())' |
    jq -er '.version | select(type == "string" and length > 0)'
}

# 3. Check the current active slot and the expected version of each slot.
printf "\n2) Current state:\n"
"$SWITCH_SH" status
ACTIVE="$("$SWITCH_SH" status | awk '/^Active slot:/ {print $3}')"
case "$ACTIVE" in
  blue) TARGET=green ;;
  green) TARGET=blue ;;
  *) printf "Error: cannot determine active slot\n" >&2; exit 1 ;;
esac
EXPECTED_BEFORE="$(slot_version "$ACTIVE")"
EXPECTED_AFTER="$(slot_version "$TARGET")"
VER_BEFORE="$(curl --fail --silent --show-error "http://localhost:${PORT}/version" | jq -er '.version | select(type == "string" and length > 0)')"
printf "Version before switch: %s\n" "$VER_BEFORE"
if [ "$VER_BEFORE" != "$EXPECTED_BEFORE" ]; then
  printf "Error: initial version does not match %s (%s)\n" "$ACTIVE" "$EXPECTED_BEFORE" >&2
  exit 1
fi

# Restore the original routing even if verification fails after the switch.
trap '"$SWITCH_SH" switch "$ACTIVE" >&2 || true' EXIT
printf "\n3) Switching to %s...\n" "$TARGET"
"$SWITCH_SH" switch "$TARGET"
sleep 2
VER_AFTER="$(curl --fail --silent --show-error "http://localhost:${PORT}/version" | jq -er '.version | select(type == "string" and length > 0)')"
printf "Version after switch: %s\n" "$VER_AFTER"
if [ "$VER_AFTER" != "$EXPECTED_AFTER" ]; then
  printf "Error: switched version does not match %s (%s)\n" "$TARGET" "$EXPECTED_AFTER" >&2
  exit 1
fi
printf "${GREEN}Target version verified: %s${RESET}\n" "$VER_AFTER"

# 4. Switch back and verify the original version.
printf "\n4) Switching back to %s (rollback)...\n" "$ACTIVE"
"$SWITCH_SH" switch "$ACTIVE"
trap - EXIT
sleep 2
VER_BACK="$(curl --fail --silent --show-error "http://localhost:${PORT}/version" | jq -er '.version | select(type == "string" and length > 0)')"
printf "Version after rollback: %s\n" "$VER_BACK"
if [ "$VER_BACK" != "$VER_BEFORE" ]; then
  printf "Error: rollback version does not match %s\n" "$VER_BEFORE" >&2
  exit 1
fi
printf "${BLUE}Rollback verified: %s${RESET}\n" "$VER_BACK"

printf "\n=== Demo check passed ===\n"
printf "The cutover is observable via curl http://localhost:%s/version before/after switch.\n" "$PORT"
printf "This script is manual and not wired into .github/workflows/ci.yml (deliberate).\n"
printf "To clean up: docker compose -f %s down -v\n" "$COMPOSE_FILE"
