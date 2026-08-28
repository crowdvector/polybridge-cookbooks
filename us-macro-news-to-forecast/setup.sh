#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3.10 or newer first." >&2
  exit 1
fi

echo "Using Python: $(command -v python3) ($(python3 --version 2>&1))"
python3 -m pip install -r requirements.txt

echo
echo "Ready. Try: python3 us_macro_news_to_forecast.py --demo inflation-ap"
