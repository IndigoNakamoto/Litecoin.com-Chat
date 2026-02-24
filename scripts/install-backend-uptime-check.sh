#!/usr/bin/env bash
#
# Install the backend uptime check as a launchd agent (runs every 60s on this Mac).
# Run from project root: ./scripts/install-backend-uptime-check.sh
# See docs/monitoring/BACKEND_UPTIME_MONITORING.md for details.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_SRC="$PROJECT_ROOT/monitoring/com.litecoin.backend-uptime-check.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.litecoin.backend-uptime-check.plist"

if [[ ! -f "$PLIST_SRC" ]]; then
  echo "❌ Plist not found: $PLIST_SRC"
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" "$PLIST_SRC" > "$PLIST_DEST"
echo "✅ Installed: $PLIST_DEST"

# Unload if already loaded, then load
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"
echo "✅ Loaded. Backend uptime check will run every 60 seconds."
echo ""
echo "Downtime log: $PROJECT_ROOT/monitoring/backend_downtime.log"
echo "View: tail -f $PROJECT_ROOT/monitoring/backend_downtime.log"
echo "Uninstall: launchctl unload $PLIST_DEST"
echo ""
