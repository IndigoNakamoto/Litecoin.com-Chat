#!/usr/bin/env bash
#
# Backend uptime checker for Mac mini production.
# Runs every minute (via launchd), checks http://localhost:8000/health,
# and logs DOWN/UP events with timestamps so you have a record of outages.
#
# Install: see docs/monitoring/BACKEND_UPTIME_MONITORING.md
# Usage: ./scripts/backend-uptime-check.sh   (or run via launchd)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STATE_FILE="$PROJECT_ROOT/monitoring/.backend_uptime_state"
LOG_FILE="$PROJECT_ROOT/monitoring/backend_downtime.log"
HEALTH_URL="${BACKEND_HEALTH_URL:-http://localhost:8000/health}"
CONNECT_TIMEOUT=10

mkdir -p "$(dirname "$STATE_FILE")"
mkdir -p "$(dirname "$LOG_FILE")"

# Current status: up if health returns 200, else down
if curl -sf --connect-timeout "$CONNECT_TIMEOUT" "$HEALTH_URL" >/dev/null 2>&1; then
  CURRENT="up"
else
  CURRENT="down"
fi

# Read previous state (default: up so we only log when we first see down)
PREVIOUS="up"
LAST_CHANGE=""
if [[ -f "$STATE_FILE" ]]; then
  PREVIOUS="$(head -n1 "$STATE_FILE" 2>/dev/null || echo up)"
  LAST_CHANGE="$(sed -n '2p' "$STATE_FILE" 2>/dev/null)"
fi

now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

# Log transition and update state file
if [[ "$CURRENT" != "$PREVIOUS" ]]; then
  NOW=$(now_iso)
  if [[ "$CURRENT" == "down" ]]; then
    echo "DOWN	$NOW	backend health check failed ($HEALTH_URL)" >> "$LOG_FILE"
    echo -e "down\n$NOW" > "$STATE_FILE"
  else
    # Back up: compute duration if we have a previous down time
    DURATION=""
    if [[ -n "$LAST_CHANGE" ]] && [[ "$PREVIOUS" == "down" ]]; then
      if command -v python3 &>/dev/null; then
        DURATION=$(python3 -c "
from datetime import datetime
a = datetime.fromisoformat('$LAST_CHANGE'.replace('Z', '+00:00'))
b = datetime.fromisoformat('$NOW'.replace('Z', '+00:00'))
d = (b - a).total_seconds()
if d >= 3600: print(f'{(d/3600):.1f}h')
elif d >= 60: print(f'{(d/60):.0f}m')
else: print(f'{d:.0f}s')
" 2>/dev/null || true)
      fi
      [[ -n "$DURATION" ]] && DURATION=" (duration ${DURATION})"
    fi
    echo "UP	$NOW	backend healthy again${DURATION}" >> "$LOG_FILE"
    echo -e "up\n$NOW" > "$STATE_FILE"
  fi
fi
