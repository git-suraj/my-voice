#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/pyinstaller" ]]; then
  echo "PyInstaller is not installed. Run: uv pip install -e '.[app]'" >&2
  exit 1
fi

rm -rf build dist
.venv/bin/pyinstaller --clean --noconfirm packaging/MyVoice.spec

if command -v codesign >/dev/null 2>&1; then
  codesign --force --deep --sign - dist/MyVoice.app
fi

echo "Built dist/MyVoice.app"
