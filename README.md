# PolyBridge Cookbooks

Runnable PolyBridge cookbooks for market-implied workflows, Colab notebooks, and developer examples. Each cookbook is self-contained and includes a standalone `README.md`, a runnable notebook, a `setup.sh` installer, helper code, and public-facing generated assets.

The blog articles use dated snapshots. Running the notebooks or scripts calls the live Forecast API, so values may differ.

## Cookbook Index

| Cookbook | What it builds | APIs / tools used | Article | Colab | GitHub folder |
| --- | --- | --- | --- | --- | --- |
| `vix-forecast/` | A five-call VIX stress monitor with one headline VIX signal and four highlighted macro drivers: oil, SPX drawdown, gold, and Hormuz reopening. | PolyBridge Forecast, Python 3.10+, `requests`, `matplotlib` | [Forecast VIX from prediction markets](https://polybridge.ai/blog/vix-forecast) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/vix-forecast) |
| `longshort-portfolio/` | A portfolio sizing workflow from PolyBridge Forecast probabilities, directional thesis inputs, and order instructions. | PolyBridge Forecast, PolyBridge MCP, Claude Desktop prompt workflow, Python 3.10+, `requests`, `pillow` | [Long-short agent portfolio from prediction market insights](https://polybridge.ai/blog/longshort-portfolio) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/longshort-portfolio) |

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

Then choose a cookbook and run it from its own directory.

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/vix-forecast
bash setup.sh
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
python3 stress_monitor.py
open assets/market-stress-monitor.png
```

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/longshort-portfolio
bash setup.sh
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
python3 portfolio_sizing.py
open assets/portfolio-summary.png
```

## Operational Note

Cookbooks produce market-implied examples from live Forecast calls. Values can change as source markets update.

## Resources

- PolyBridge Developer Console: https://polybridge.ai/console
- PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4
- VIX forecast article: https://polybridge.ai/blog/vix-forecast
- Long-short agent portfolio article: https://polybridge.ai/blog/longshort-portfolio
