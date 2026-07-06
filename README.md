# PolyBridge Cookbooks

Runnable PolyBridge cookbooks for market-implied workflows, Colab notebooks, and developer examples. Each cookbook is self-contained and includes a standalone `README.md`, a runnable notebook, a `setup.sh` installer, helper code, and public-facing generated assets.

The Forecast blog articles use dated snapshots. Running those notebooks or scripts calls the live Forecast API, so values may differ. The Agentic Finance cookbook is offline-first and uses SimBroker for an account-free simulated paper workflow.

## Cookbook Index

| Cookbook | What it builds | APIs / tools used | Article | Colab | GitHub folder |
| --- | --- | --- | --- | --- | --- |
| `vix-forecast/` | A five-call VIX stress monitor over the next quarter (next 90 days), with one headline VIX signal and four highlighted macro drivers: oil, SPX drawdown, gold, and Hormuz regular traffic. | PolyBridge Forecast, Python 3.10+, `requests`, `matplotlib` | [Forecast VIX from prediction markets](https://polybridge.ai/research/vix-forecast) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/vix-forecast/vix-forecast.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/vix-forecast) |
| `longshort-portfolio/` | Reconstruct market-implied price distributions from Forecast price thresholds, size via half-Kelly, and output Hyperliquid 1x perp order instructions. | PolyBridge Forecast, Python 3.10+, `requests` | [Long-short portfolio on Hyperliquid from prediction market prices](https://polybridge.ai/research/longshort-portfolio) | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/longshort-portfolio) |
| `agentic-finance/` | Market Foresight Before Trading: replay a labor-market thesis through PolyBridge-style probabilities, an Evidence Gate, and a SimBroker SPY paper trade. | Offline replay, SimBroker, Python 3.9+, stdlib `unittest` |  | [Open notebook](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/agentic-finance/agentic-finance.ipynb) | [View folder](https://github.com/crowdvector/polybridge-cookbooks/tree/main/agentic-finance) |

## Repo Layout

- `README.md` is the public index for the repo.
- `PROMPT.md` files capture the reproduction brief or MCP prompt for each cookbook.
- `.ipynb` notebooks are designed for local Jupyter use or Google Colab.
- `setup.sh` installs the cookbook-specific Python dependencies.
- `assets/` contains the generated public artifacts used by each example.

## Setup

These cookbooks run without an API key.

Python 3.10+ is required (the `agentic-finance` recorded demo runs on Python 3.9+ with no extra packages).

Choose a cookbook and run it from its own directory.

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/vix-forecast
bash setup.sh
python3 stress_monitor.py
open assets/market-stress-monitor.png
```

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/longshort-portfolio
bash setup.sh
python3 portfolio.py
```

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/agentic-finance
bash demo.sh
```

## Operational Note

Forecast cookbooks produce market-implied examples from live Forecast calls. Values can change as source markets update. The Agentic Finance Evidence Gate cookbook is research/demo software, not financial advice, and defaults to sanitized offline fixtures.

## Resources

- PolyBridge Developer Console: https://polybridge.ai/console
- PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4
- VIX forecast article: https://polybridge.ai/research/vix-forecast
- Long-short portfolio article: https://polybridge.ai/research/longshort-portfolio
