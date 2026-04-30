#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

scripts/install_launch_agent.sh

cat <<DONE

Restarted MyVoice LaunchAgent.

Check for permission warnings:
  tail -n 30 "$HOME/Library/Logs/my-voice/app.log"
DONE
