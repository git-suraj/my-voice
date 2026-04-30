#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_PATH="${1:-"$ROOT_DIR/dist/MyVoice.app"}"
LABEL="com.myvoice.app"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$PLIST_DIR/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/my-voice"
UID_VALUE="$(id -u)"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App not found: $APP_PATH" >&2
  echo "Build it first: scripts/install.sh" >&2
  exit 1
fi

EXECUTABLE="$APP_PATH/Contents/MacOS/MyVoice"
if [[ ! -x "$EXECUTABLE" ]]; then
  echo "App executable not found or not executable: $EXECUTABLE" >&2
  exit 1
fi

mkdir -p "$PLIST_DIR" "$LOG_DIR"

launchctl bootout "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true
launchctl bootout "gui/$UID_VALUE" "$PLIST_PATH" >/dev/null 2>&1 || true
pkill MyVoice 2>/dev/null || true

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
      <string>/usr/bin/open</string>
      <string>-W</string>
      <string>-n</string>
      <string>$APP_PATH</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$LOG_DIR/launchagent.out.log</string>

    <key>StandardErrorPath</key>
    <string>$LOG_DIR/launchagent.err.log</string>

    <key>WorkingDirectory</key>
    <string>$ROOT_DIR</string>
  </dict>
</plist>
PLIST

chmod 644 "$PLIST_PATH"
plutil -lint "$PLIST_PATH" >/dev/null

launchctl enable "gui/$UID_VALUE/$LABEL" >/dev/null 2>&1 || true

if ! BOOTSTRAP_OUTPUT="$(launchctl bootstrap "gui/$UID_VALUE" "$PLIST_PATH" 2>&1)"; then
  cat >&2 <<ERROR
Failed to bootstrap LaunchAgent.

launchctl output:
$BOOTSTRAP_OUTPUT

Plist:
  $PLIST_PATH

App:
  $APP_PATH

Try:
  launchctl bootout gui/$UID_VALUE/$LABEL
  launchctl bootout gui/$UID_VALUE "$PLIST_PATH"
  scripts/install_launch_agent.sh

For more detail:
  plutil -p "$PLIST_PATH"
  tail -n 50 "$LOG_DIR/launchagent.err.log"
ERROR
  exit 1
fi
launchctl enable "gui/$UID_VALUE/$LABEL"
launchctl kickstart -k "gui/$UID_VALUE/$LABEL"

cat <<DONE
Installed and started LaunchAgent:
  $PLIST_PATH

App:
  $APP_PATH

Check status:
  scripts/launch_agent_status.sh

Watch app log:
  tail -f "$LOG_DIR/app.log"
DONE
