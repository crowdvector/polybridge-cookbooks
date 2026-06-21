# PolyBridge Cookbooks

Runnable PolyBridge cookbooks for market-implied workflows, Colab notebooks, and developer examples. Each cookbook is self-contained and includes a standalone `README.md`, a runnable notebook, a `setup.sh` installer, helper code, and public-facing generated assets.

The blog articles use dated snapshots. Running the notebooks or scripts calls the live Forecast API, so values may differ.

## Cookbook Index

| Cookbook | What it builds | APIs / tools used | Article | Colab | GitHub folder |
| --- | --- | --- | --- | --- | --- |
| `vix-forecast/` | A five-call VIX stress monitor for the next 2 months (~42 trading days), with one headline VIX signal and four highlighted macro drivers: oil, SPX drawdown, gold, and Hormuz reopening. | PolyBridge Forecast, Python 3.10+, `requests`, `matplotlib` | [Forecast VIX from prediction markets](https://polybridge.ai/research/vix-forecast) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/vix-forecast) |
| `longshort-portfolio/` | Reconstruct market-implied price distributions from Forecast price thresholds, size via half-Kelly, and output Hyperliquid 1x perp order instructions. | PolyBridge Forecast, Python 3.10+, `requests` | [Long-short portfolio on Hyperliquid from prediction market prices](https://polybridge.ai/research/longshort-portfolio) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/longshort-portfolio) |

## Repo Layout

- `README.md` is the public index for the repo.
- `PROMPT.md` files capture the reproduction brief or MCP prompt for each cookbook.
- `.ipynb` notebooks are designed for local Jupyter use or Google Colab.
- `setup.sh` installs the cookbook-specific Python dependencies.
- `assets/` contains the generated public artifacts used by each example.

## Setup

These cookbooks run without an API key at anonymous limits. Add an API key for higher usage.

Python 3.10+ is required. `POLYBRIDGE_API_KEY` is optional.

Choose a cookbook and run it from its own directory.

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/vix-forecast
bash setup.sh

# Optional. Leave unset to use anonymous limits.
# export POLYBRIDGE_API_KEY="your_api_key_here"

python3 stress_monitor.py
open assets/market-stress-monitor.png
```

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/longshort-portfolio
bash setup.sh

# Optional. Leave unset to use anonymous limits.
# export POLYBRIDGE_API_KEY="your_api_key_here"

python3 portfolio.py
```

## Operational Note

Cookbooks produce market-implied examples from live Forecast calls. Values can change as source markets update.

## Resources

- PolyBridge Developer Console: https://polybridge.ai/console
- PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4
- VIX forecast article: https://polybridge.ai/research/vix-forecast
- Long-short portfolio article: https://polybridge.ai/research/longshort-portfolio
