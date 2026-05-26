# Forecast VIX from prediction markets

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb)

Use PolyBridge Forecast to build a live market snapshot around VIX and related stress questions that are not all directly listed on a single venue.

## Quick Links

- Article: https://polybridge.ai/blog/vix-forecast
- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/vix-forecast

## What this cookbook builds

This cookbook runs five live forecast questions against `POST https://api.polybridge.ai/v1/forecast`, writes a sanitized snapshot to `assets/snapshot.json`, and renders a dark-theme hero image to `assets/market-stress-monitor.png`.

Questions used in this cookbook:

- Will VIX close above 30 in the next 42 days?
- Will crude oil settle above $90 in June 2026?
- Will SPX draw down more than 10% in the next 42 days?
- Will gold rise more than 10% in the next 42 days?
- Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?

## Files

- `stress_monitor.py` runs the live workflow, retries on `429` and `503`, sanitizes the response, and renders the PNG.
- `vix-forecast.ipynb` mirrors the same workflow in notebook form and uses `getpass` if the API key is not already set.
- `setup.sh` installs the minimal local dependencies.
- `PROMPT.md` is the reproduction brief for adapting the cookbook.
- `assets/` stores the generated snapshot and image output.

## Dependencies

- Python 3
- `requests`
- `matplotlib`

## API key handling

Script mode expects `POLYBRIDGE_API_KEY` to already be present in the environment:

```bash
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
```

Notebook mode checks the environment first and falls back to `getpass()` only if the variable is missing. The key is never printed, saved into files, or included in the generated assets.

## Run locally

From the cookbook directory:

```bash
cd vix-forecast
./setup.sh
python3 stress_monitor.py
```

The workflow is sequential, uses a 75 second request timeout, and retries with backoff when the API returns `429` or `503`. If the service provides `Retry-After`, that value is honored instead of using a fixed sleep. There is no baked-in fixed-delay public-tier assumption in this version.

## Outputs

- `assets/snapshot.json` contains the UTC timestamp, endpoint metadata, question-level probabilities, optional reasoning or interval data, and sanitized source markets.
- `assets/market-stress-monitor.png` is a dark theme horizontal bar chart suitable for the eventual article hero image.

## Notes

These outputs are market-implied snapshots, not financial advice. They can change as the underlying prediction markets update.
