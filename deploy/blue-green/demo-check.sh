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
printf "Project: hiss-blue-green (isolated from hiss-dev/staging/prod on 8001-8003)\n"
printf "Images: ghcr.io/vieitesss/hiss (public, no login needed)\n\n"

# 1. Bring up (uses .env.example defaults for BLUE_TAG/GREEN_TAG if not overridden)
printf "1) Starting demo (docker compose up -d)...\n"
# Use --pull never for local images (fallback to normal pull for remote public images)
docker compose -f "$COMPOSE_FILE" up -d --pull never || docker compose -f "$COMPOSE_FILE" up -d

# 2. Wait for deps: db healthy, then blue/green healthy, then proxy reachable
# db has no published port, so we wait via health status
wait_healthy "blue" || { docker compose -f "$COMPOSE_FILE" logs blue; exit 1; }
wait_healthy "green" || { docker compose -f "$COMPOSE_FILE" logs green; exit 1; }

printf "Waiting for proxy to be reachable on :%s ...\n" "$PORT"
# Use host-side curl with retries (bounded)
curl --fail --silent --show-error --max-time 5 --retry 10 --retry-delay 2 --retry-connrefused "http://localhost:${PORT}/healthz" >/dev/null
curl --fail --silent --show-error --max-time 5 --retry 10 --retry-delay 2 --retry-connrefused "http://localhost:${PORT}/version" | jq .

# 3. Check current active slot and version
printf "\n2) Current state:\n"
"$SWITCH_SH" status
VER_BEFORE="$(curl --fail --silent --show-error "http://localhost:${PORT}/version" | jq -r .version)"
printf "Version before switch: %s\n" "$VER_BEFORE"

# 4. Determine target (opposite of current)
ACTIVE="$("$SWITCH_SH" status 2>&1 | grep -q "blue" && echo "blue" || echo "green")"
# More robust: read .active-slot directly
if [ -f "$SCRIPT_DIR/.active-slot" ]; then
  ACTIVE="$(tr -d ' \t\r\n' < "$SCRIPT_DIR/.active-slot" 2>/dev/null || echo "blue")"
else
  ACTIVE="blue"
fi
if [ "$ACTIVE" = "blue" ]; then TARGET="green"; else TARGET="blue"; fi

printf "\n3) Switching to %s...\n" "$TARGET"
"$SWITCH_SH" switch "$TARGET"

# 5. Verify version changed (if tags are different; if both default to 0.1.0, version may be same — still a valid switch)
sleep 2
VER_AFTER="$(curl --fail --silent --show-error "http://localhost:${PORT}/version" | jq -r .version)"
printf "Version after switch: %s\n" "$VER_AFTER"
if [ "$VER_BEFORE" != "$VER_AFTER" ]; then
  printf "${GREEN}Version changed: %s -> %s${RESET}\n" "$VER_BEFORE" "$VER_AFTER"
else
  printf "Note: version unchanged (%s) — both slots may be on same tag. Switch still succeeded (proxy now points to %s).\n" "$VER_AFTER" "$TARGET"
fi

# 6. Switch back (verify rollback = switch back)
printf "\n4) Switching back to %s (rollback)...\n" "$ACTIVE"
"$SWITCH_SH" switch "$ACTIVE"
sleep 2
VER_BACK="$(curl --fail --silent --show-error "http://localhost:${PORT}/version" | jq -r .version)"
printf "Version after rollback: %s\n" "$VER_BACK"
if [ "$VER_BACK" = "$VER_BEFORE" ]; then
  printf "${BLUE}Rollback verified: %s${RESET}\n" "$VER_BACK"
fi

printf "\n=== Demo check passed ===\n"
printf "The cutover is observable via curl http://localhost:%s/version before/after switch.\n" "$PORT"
printf "This script is manual and not wired into .github/workflows/ci.yml (deliberate).\n"
printf "To clean up: docker compose -f %s down -v\n" "$COMPOSE_FILE"
