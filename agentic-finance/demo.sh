#!/usr/bin/env bash
# Market Foresight Before Trading — recorded demo launcher.
# Runs the Tier 1 Evidence Gate replay, then the Tier 3 SimBroker paper trader.
# Needs only Python 3.9+. No pip, no API key, no account, no network, no real trading.
set -e

cd "$(dirname "$0")"

MIN_MAJOR=3
MIN_MINOR=9

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ]; then
  echo "Python was not found." >&2
  echo "Install Python 3.9 or newer (https://www.python.org/downloads/) and re-run bash demo.sh." >&2
  echo "On macOS: brew install python. On Debian/Ubuntu: sudo apt install python3." >&2
  exit 1
fi

if ! "$PY" -c "import sys; sys.exit(0 if sys.version_info >= ($MIN_MAJOR, $MIN_MINOR) else 1)"; then
  echo "This demo needs Python $MIN_MAJOR.$MIN_MINOR or newer." >&2
  echo "Found: $("$PY" --version 2>&1) at $(command -v "$PY")" >&2
  echo "Install a newer Python, or run the notebook in Colab instead." >&2
  exit 1
fi

echo "Using Python: $(command -v "$PY") ($("$PY" --version 2>&1))"
echo "Replay mode: recorded data only. No API key, no account, no network, no real trading."
echo

echo "=== Tier 1: Evidence Gate (recorded replay) ==="
"$PY" tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay examples/recorded_run_2026-07-04.json

echo
echo "=== Tier 3: SimBroker paper trader (simulated) ==="
echo "SimBroker is a local pretend broker. It will show a preview and ask for y/N confirmation."
echo "Nothing is real: y records a simulated fill to a local file; anything else declines."
echo
"$PY" tier3_paper_trader.py --thesis labor-resilience-jul2026 --replay examples/recorded_run_2026-07-04.json
