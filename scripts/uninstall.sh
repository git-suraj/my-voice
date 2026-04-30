#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REMOVE_CONFIG=false
REMOVE_LOGS=false
REMOVE_VENV=false
REMOVE_MODELS=false

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
    --models)
      REMOVE_MODELS=true
      ;;
    --all)
      REMOVE_CONFIG=true
      REMOVE_LOGS=true
      REMOVE_VENV=true
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/uninstall.sh [--config] [--logs] [--venv] [--models] [--all]

Stops MyVoice and removes local app build artifacts.

Options:
  --config  also remove app config, but preserve Application Support models
  --logs    also remove ~/Library/Logs/my-voice
  --venv    also remove .venv
  --models  also remove ~/Library/Application Support/my-voice/models
  --all     remove config, logs, and .venv too; models are still preserved

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
  app_support="$HOME/Library/Application Support/my-voice"
  if [[ -d "$app_support" ]]; then
    find "$app_support" -mindepth 1 -maxdepth 1 ! -name models -exec rm -rf {} +
  fi
fi

if [[ "$REMOVE_MODELS" == true ]]; then
  rm -rf "$HOME/Library/Application Support/my-voice/models"
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
