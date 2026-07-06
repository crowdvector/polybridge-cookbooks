#!/usr/bin/env bash
# Installs optional dependencies for live PolyBridge mode and custom workflows.
# The recorded demo does not need setup.sh. Use bash demo.sh for the quickstart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3.9 or newer first." >&2
  exit 1
fi

echo "Using Python: $(command -v python3) ($(python3 --version 2>&1))"
echo "Installing live-mode dependencies with: python3 -m pip install --user -r requirements.txt"
python3 -m pip install --user -r requirements.txt

echo
echo "Done. Note: the recorded demo does not need setup.sh. Use bash demo.sh for the quickstart."
