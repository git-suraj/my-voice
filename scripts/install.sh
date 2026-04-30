#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INSTALL_LAUNCH_AGENT=true
RESET_PERMISSIONS=true

for arg in "$@"; do
  case "$arg" in
    --no-launch-agent)
      INSTALL_LAUNCH_AGENT=false
      ;;
    --no-permission-reset)
      RESET_PERMISSIONS=false
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/install.sh [--no-launch-agent] [--no-permission-reset]

Installs Python/app dependencies, builds dist/MyVoice.app, and installs the
LaunchAgent so MyVoice starts on login and restarts if it exits.

Options:
  --no-launch-agent      build the app without installing the LaunchAgent
  --no-permission-reset  keep existing macOS privacy permission entries
USAGE
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it first: https://docs.astral.sh/uv/" >&2
  exit 1
fi

if [[ ! -x ".venv/bin/python" ]]; then
  uv venv --seed .venv
fi

uv pip install -e ".[app]"
chmod +x scripts/build_macos_app.sh
scripts/build_macos_app.sh

if [[ "$RESET_PERMISSIONS" == true ]]; then
  chmod +x scripts/reset_macos_permissions.sh
  scripts/reset_macos_permissions.sh
fi

if [[ "$INSTALL_LAUNCH_AGENT" == true && "$RESET_PERMISSIONS" == false ]]; then
  chmod +x scripts/install_launch_agent.sh
  scripts/install_launch_agent.sh
fi

cat <<DONE

Install complete.

App:
  $ROOT_DIR/dist/MyVoice.app

Next steps:
  1. Make sure Ollama is running if you want polished cleanup:
     ollama serve

  2. Re-add MyVoice in:
     System Settings -> Privacy & Security -> Accessibility
     System Settings -> Privacy & Security -> Input Monitoring
     System Settings -> Privacy & Security -> Microphone

     This install reset stale macOS permission entries, so you may need to
     re-enable MyVoice even if it was enabled before.

  3. After granting permissions, start MyVoice:
     scripts/restart_launch_agent.sh

  4. Check background status:
     scripts/launch_agent_status.sh

  5. Watch the app log:
     tail -f "$HOME/Library/Logs/my-voice/app.log"

Uninstall:
  scripts/uninstall.sh
DONE
