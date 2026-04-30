#!/usr/bin/env bash
set -euo pipefail

BUNDLE_ID="com.local.myvoice"
LABEL="com.myvoice.app"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_VALUE="$(id -u)"

cat <<START
Resetting macOS privacy permissions for MyVoice.

Bundle id:
  $BUNDLE_ID

This removes stale TCC entries. You must re-enable MyVoice in System Settings
after running this script.
START

launchctl bootout "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE" "$PLIST_PATH" >/dev/null 2>&1 || true
pkill MyVoice 2>/dev/null || true

tccutil reset Accessibility "$BUNDLE_ID" >/dev/null 2>&1 || true
tccutil reset ListenEvent "$BUNDLE_ID" >/dev/null 2>&1 || true
tccutil reset Microphone "$BUNDLE_ID" >/dev/null 2>&1 || true
tccutil reset AppleEvents "$BUNDLE_ID" >/dev/null 2>&1 || true

cat <<DONE

Done.

Next steps:
  1. Re-enable MyVoice in:
     System Settings -> Privacy & Security -> Accessibility
     System Settings -> Privacy & Security -> Input Monitoring
     System Settings -> Privacy & Security -> Microphone

  2. Restart MyVoice after granting permissions:
     scripts/restart_launch_agent.sh

  3. Watch the app log:
     tail -f "$HOME/Library/Logs/my-voice/app.log"
DONE
