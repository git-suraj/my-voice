#!/usr/bin/env bash
set -euo pipefail

LABEL="com.myvoice.app"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

launchctl bootout "gui/$UID_VALUE" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl disable "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"
pkill MyVoice 2>/dev/null || true
pkill -f "MyVoice.app/Contents/MacOS/MyVoice" 2>/dev/null || true
pkill -f "open -W -n .*MyVoice.app" 2>/dev/null || true
pkill -9 -f "MyVoice.app/Contents/MacOS/MyVoice" 2>/dev/null || true

cat <<DONE
Removed LaunchAgent:
  $PLIST_PATH

The app bundle, config, and logs were not removed.
Use scripts/uninstall.sh if you also want to remove build artifacts.
DONE
