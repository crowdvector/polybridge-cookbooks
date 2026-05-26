# PolyBridge Cookbooks

Runnable PolyBridge cookbooks for market-implied workflows, Colab notebooks, and developer examples. Each cookbook is self-contained and includes a standalone `README.md`, a runnable notebook, a `setup.sh` installer, helper code, and public-facing generated assets.

## Cookbook Index

| Cookbook | What it builds | APIs / tools used | Article | Colab | GitHub folder |
| --- | --- | --- | --- | --- | --- |
| `vix-forecast/` | A live market stress snapshot for VIX, oil, SPX drawdown, gold, and Hormuz reopening probabilities. | PolyBridge Forecast, Python, `requests`, `matplotlib` | [VIX forecast](https://polybridge.ai/blog/vix-forecast) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/vix-forecast) |
| `portfolio-allocation/` | A market-implied allocation workflow across `SPY`, `TLT`, `GLD`, `XLE`, and `VIXY` with optimizer outputs and charts. | PolyBridge Forecast, Yahoo Finance, Python, `pandas`, `numpy`, `scipy`, `matplotlib`, `yfinance` | [Portfolio allocation](https://polybridge.ai/blog/portfolio-allocation) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/portfolio-allocation/portfolio-allocation.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/portfolio-allocation) |
| `longshort-portfolio/` | A dry-run, review-only long/short sizing demo with structured order-intent artifacts and an MCP prompt workflow. | PolyBridge Forecast, PolyBridge MCP, Claude Desktop prompt workflow, Python, `requests`, `pillow` | [Long/short dry run](https://polybridge.ai/blog/longshort-portfolio) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/longshort-portfolio) |

## Repo Layout

- `README.md` is the public index for the repo.
- `PROMPT.md` files capture the reproduction brief or MCP prompt for each cookbook.
- `.ipynb` notebooks are designed for local Jupyter use or Google Colab.
- `setup.sh` installs the cookbook-specific Python dependencies.
- `assets/` contains the generated public artifacts used by each example.

## Setup

Get a PolyBridge Forecast API key from the PolyBridge Developer Console:

- https://polybridge.ai/console

Export it before running the forecast-backed cookbooks:

```bash
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
```

Then choose a cookbook and run its setup script from the repo root:

```bash
./vix-forecast/setup.sh
python3 vix-forecast/stress_monitor.py
```

```bash
./portfolio-allocation/setup.sh
python3 portfolio-allocation/portfolio_optimizer.py
```

```bash
./longshort-portfolio/setup.sh
python3 longshort-portfolio/dry_run_portfolio.py
```

## Safety

- Forecast outputs are market-implied snapshots derived from prediction-market data.
- The values in `assets/` can change as source markets update.
- These cookbooks are technical examples and are not financial advice.
- `longshort-portfolio/` is dry-run and review-only. It does not place trades, require private keys, or include live execution code.

## Resources

- PolyBridge Developer Console: https://polybridge.ai/console
- PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4
- VIX forecast article: https://polybridge.ai/blog/vix-forecast
- Portfolio allocation article: https://polybridge.ai/blog/portfolio-allocation
- Long/short dry-run article: https://polybridge.ai/blog/longshort-portfolio
