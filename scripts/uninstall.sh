#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOVE_CONFIG=false
REMOVE_LOGS=false
REMOVE_VENV=false

for arg in "$@"; do
  case "$arg" in
    --config)
      REMOVE_CONFIG=true
      ;;
    --logs)
      REMOVE_LOGS=true
      ;;
    --venv)
      REMOVE_VENV=true
      ;;
    --all)
      REMOVE_CONFIG=true
      REMOVE_LOGS=true
      REMOVE_VENV=true
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/uninstall.sh [--config] [--logs] [--venv] [--all]

Stops MyVoice and removes local app build artifacts.

Options:
  --config  also remove ~/.config/my-voice and ~/Library/Application Support/my-voice
  --logs    also remove ~/Library/Logs/my-voice
  --venv    also remove .venv
  --all     remove config, logs, and .venv too

macOS privacy permissions must be removed manually in System Settings.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

scripts/uninstall_launch_agent.sh >/dev/null 2>&1 || true
pkill MyVoice 2>/dev/null || true
pkill -f "MyVoice.app/Contents/MacOS/MyVoice" 2>/dev/null || true
pkill -f "open -W -n .*MyVoice.app" 2>/dev/null || true
pkill -9 -f "MyVoice.app/Contents/MacOS/MyVoice" 2>/dev/null || true

rm -rf dist/MyVoice.app
rm -rf build dist
rm -rf my_voice.egg-info

if [[ "$REMOVE_CONFIG" == true ]]; then
  rm -rf "$HOME/.config/my-voice"
  rm -rf "$HOME/Library/Application Support/my-voice"
fi

if [[ "$REMOVE_LOGS" == true ]]; then
  rm -rf "$HOME/Library/Logs/my-voice"
fi

if [[ "$REMOVE_VENV" == true ]]; then
  rm -rf .venv
fi

cat <<'DONE'
Uninstall complete.

If MyVoice appears in macOS privacy settings, remove or disable it manually:
  System Settings -> Privacy & Security -> Accessibility
  System Settings -> Privacy & Security -> Input Monitoring
  System Settings -> Privacy & Security -> Microphone
DONE
