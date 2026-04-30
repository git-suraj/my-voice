#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INSTALL_LAUNCH_AGENT=true
RESET_PERMISSIONS=true
SETUP_OLLAMA=true
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:1.5b}"
OLLAMA_URL="${OLLAMA_URL:-http://127.0.0.1:11434}"

for arg in "$@"; do
  case "$arg" in
    --no-launch-agent)
      INSTALL_LAUNCH_AGENT=false
      ;;
    --no-permission-reset)
      RESET_PERMISSIONS=false
      ;;
    --no-ollama)
      SETUP_OLLAMA=false
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/install.sh [--no-launch-agent] [--no-permission-reset] [--no-ollama]

Installs Python/app dependencies, builds dist/MyVoice.app, and installs the
LaunchAgent so MyVoice starts on login and restarts if it exits.

Options:
  --no-launch-agent      build the app without installing the LaunchAgent
  --no-permission-reset  keep existing macOS privacy permission entries
  --no-ollama            skip Ollama/Qwen readiness checks

Environment:
  OLLAMA_MODEL           model to pull/warm, default qwen2.5:1.5b
  OLLAMA_URL             Ollama base URL, default http://127.0.0.1:11434
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

if [[ "$SETUP_OLLAMA" == true ]]; then
  if ! command -v ollama >/dev/null 2>&1; then
    cat >&2 <<'OLLAMA_MISSING'
Ollama is required for polished cleanup but was not found.

Install it first:
  brew install --cask ollama

Then rerun:
  scripts/install.sh

Or skip this check:
  scripts/install.sh --no-ollama
OLLAMA_MISSING
    exit 1
  fi

  if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    echo "Starting Ollama server..."
    mkdir -p "$HOME/Library/Logs/my-voice"
    nohup ollama serve >>"$HOME/Library/Logs/my-voice/ollama.log" 2>&1 &
    for _ in {1..30}; do
      if curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi

  if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    echo "Ollama did not become reachable at $OLLAMA_URL" >&2
    echo "Check: $HOME/Library/Logs/my-voice/ollama.log" >&2
    exit 1
  fi

  if ! ollama list | awk '{print $1}' | grep -Fx "$OLLAMA_MODEL" >/dev/null 2>&1; then
    echo "Pulling Ollama model: $OLLAMA_MODEL"
    ollama pull "$OLLAMA_MODEL"
  fi

  if ! ollama ps | awk '{print $1}' | grep -Fx "$OLLAMA_MODEL" >/dev/null 2>&1; then
    echo "Warming Ollama model: $OLLAMA_MODEL"
    curl -fsS "$OLLAMA_URL/api/generate" \
      -H "Content-Type: application/json" \
      -d "{\"model\":\"$OLLAMA_MODEL\",\"prompt\":\"\",\"stream\":false,\"keep_alive\":\"30m\"}" \
      >/dev/null
  fi
fi

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
  1. Ollama polished cleanup:
     model: $OLLAMA_MODEL
     status: ollama ps

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
