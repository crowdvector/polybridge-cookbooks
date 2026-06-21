# Forecast VIX from prediction markets

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb)

Use PolyBridge Forecast to build a market-implied stress snapshot from one headline VIX-spike question and four highlighted macro drivers.

## Quick Links

- Article: https://polybridge.ai/research/vix-forecast
- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/vix-forecast

## What this cookbook builds

This cookbook runs five live forecast questions against `POST https://api.polybridge.ai/v1/forecast`, writes a sanitized snapshot to `assets/snapshot.json`, and renders a dark-theme hero image to `assets/market-stress-monitor.png`.

Runtime is usually 2-5 minutes. Allow up to 10 minutes with retries. The research article uses a dated snapshot; running the notebook or script calls the live Forecast API, so outputs may differ.

The VIX, SPX, and gold questions use a next 2 months (~42 trading days) horizon to match a traditional-index two-month window.

The first question is the headline signal:

- Will VIX close above 30 at least once in the next 42 trading days?

The remaining four questions are the highlighted macro drivers:

- Will crude oil settle above $90 in June 2026?
- Will SPX draw down more than 10% at any point in the next 42 trading days?
- Will gold rise more than 10% from its current price at any point in the next 42 trading days?
- Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?

## Files

- `stress_monitor.py` runs the live workflow, retries on `429` and `503`, sanitizes the response, and renders the PNG.
- `vix-forecast.ipynb` mirrors the same workflow in notebook form and can prompt for an optional API key.
- `setup.sh` installs the minimal local dependencies.
- `PROMPT.md` is the reproduction brief for adapting the cookbook.
- `assets/` stores the generated snapshot and image output.

## Dependencies

- Python 3.10+
- `requests`
- `matplotlib`

## API key handling

The VIX cookbook runs without an API key at anonymous limits. Add an API key for higher usage by setting `POLYBRIDGE_API_KEY`:

```bash
# Optional. Leave unset to use anonymous limits.
# export POLYBRIDGE_API_KEY="your_api_key_here"
```

Notebook mode checks the environment first and can prompt for an optional key. Paste a key for higher usage, or leave the prompt blank to use anonymous limits. No secrets should be committed. The key is never printed, saved into files, or included in the generated assets.

## Run locally

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/vix-forecast
bash setup.sh

# Optional. Leave unset to use anonymous limits.
# export POLYBRIDGE_API_KEY="your_api_key_here"

python3 stress_monitor.py
open assets/market-stress-monitor.png
```

The workflow is sequential, uses a 75 second request timeout, and retries with backoff when the API returns `429` or `503`. If the service provides `Retry-After`, that value is honored instead of using a fixed sleep. If a configured API key is rejected with `401` or `403`, the script stops and reports the auth failure instead of retrying anonymously.

Forecast API responses should be treated as returning fields such as `probability`, `confidence`, `confidence_interval`, and `markets_used`. The cookbook snapshot derives its displayed source-market count from `markets_used`; `source_market_count` is not assumed to be a top-level field returned by `POST /v1/forecast`.

## Outputs

- `assets/snapshot.json` contains the UTC timestamp, endpoint metadata, question-level probabilities, optional reasoning or confidence interval data, sanitized source markets, and a derived source-market count.
- `assets/market-stress-monitor.png` is a dark theme horizontal bar chart suitable for the eventual article hero image.

## Notes

These outputs are market-implied snapshots. They can change as the underlying prediction markets update.
