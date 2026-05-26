# Portfolio Allocation From Prediction Markets

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/portfolio-allocation/portfolio-allocation.ipynb)

Use PolyBridge Forecast probabilities to build a live portfolio allocation snapshot across `SPY`, `TLT`, `GLD`, `XLE`, and `VIXY`.

## Quick Links

- Article: https://polybridge.ai/blog/portfolio-allocation
- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/portfolio-allocation/portfolio-allocation.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/portfolio-allocation

## What This Cookbook Builds

This cookbook:

- queries `POST https://api.polybridge.ai/v1/forecast` for three macro scenarios
- queries fifteen conditional asset questions tied to those scenarios
- downloads two years of adjusted daily prices from Yahoo Finance
- computes daily returns and an annualized covariance matrix
- converts forecast probabilities into scenario-conditional expected returns via `E[r] = p x threshold`
- optimizes a long-only, fully invested max-Sharpe allocation with 2%-40% asset bounds
- writes a sanitized snapshot plus supporting charts to `portfolio-allocation/assets/`

## Files

- `portfolio_optimizer.py` runs the live workflow, retries on `429` and `503`, honors `Retry-After`, and renders the output assets.
- `portfolio-allocation.ipynb` reproduces the workflow in notebook form and uses `getpass()` only if `POLYBRIDGE_API_KEY` is missing from the environment.
- `setup.sh` installs the local Python dependencies.
- `PROMPT.md` is the reproduction brief for adapting the cookbook.
- `assets/` stores the generated snapshot, summary, CSV, and charts.

## Dependencies

- Python 3
- `requests`
- `pandas`
- `numpy`
- `scipy`
- `matplotlib`
- `yfinance`

## Generated Outputs

- `assets/snapshot.json`
- `assets/allocation-summary.json`
- `assets/covariance-matrix.csv`
- `assets/scenario-probabilities.png`
- `assets/implied-return-distributions.png`
- `assets/allocation-output.png`

## API Key Handling

Script mode expects `POLYBRIDGE_API_KEY` to already be present in the environment:

```bash
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
```

Notebook mode checks the environment first and only falls back to `getpass()` if the variable is missing. The key is never printed, saved into files, written into notebook outputs, or included in generated assets.

## Run Locally

From the cookbook directory:

```bash
cd portfolio-allocation
./setup.sh
python3 portfolio_optimizer.py
```

The workflow is sequential, keeps only one request in flight at a time, spaces requests to stay under the public 10-per-minute assumption, and retries with backoff when the API returns `429` or `503`. If the service provides `Retry-After`, that value is honored instead of using a fixed pacing hack.

## Notes

These outputs are market-implied snapshots, not financial advice. The probabilities, implied returns, and resulting allocation can change whenever the underlying prediction markets or price history change.
