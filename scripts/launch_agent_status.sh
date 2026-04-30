#!/usr/bin/env bash
set -euo pipefail

LABEL="com.myvoice.app"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

echo "LaunchAgent plist:"
if [[ -f "$PLIST_PATH" ]]; then
  echo "  $PLIST_PATH"
else
  echo "  not installed"
fi

echo
echo "launchctl status:"
if ! launchctl print "gui/$UID_VALUE/$LABEL"; then
  echo "  not loaded"
fi

echo
echo "MyVoice processes:"
pgrep -fl MyVoice || echo "  no MyVoice process found"
