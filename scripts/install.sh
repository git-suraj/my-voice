#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

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

