# Long-short agent portfolio from prediction market insights

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb)

Use PolyBridge Forecast probabilities to map a directional long-short thesis into a timestamped market snapshot, constrained portfolio sizing table, and order instructions for `BTC`, `SPX`, `OP`, `BERA`, and `WTI`.

## Quick Links

- Article: https://polybridge.ai/blog/longshort-portfolio
- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/longshort-portfolio
- PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4

## What This Cookbook Builds

This cookbook:

- asks the same five macro questions used in the blog article
- generates a reproducible macro snapshot from `POST https://api.polybridge.ai/v1/forecast`
- applies a constrained scoring rule with a `$50,000` gross notional budget
- writes structured JSON and markdown assets for the article and notebook
- outputs order instructions JSON with USD notional targets

## Claude/MCP vs REST Helper

There are two workflows in this cookbook:

- `PROMPT.md` is the interactive Claude Desktop + PolyBridge MCP workflow. It is for exploratory agent use, thesis challenges, and conversational review.
- `portfolio_sizing.py` is the reproducible REST-backed helper. It calls the Forecast endpoint sequentially, retries `429` and `503` with `Retry-After`, sanitizes the responses, and writes the assets used in this cookbook.

## Files

- `portfolio_sizing.py` runs the reproducible long-short portfolio sizing workflow and writes the article assets.
- `longshort-portfolio.ipynb` explains the Claude/MCP setup and runs the REST-backed helper from notebook mode.
- `setup.sh` installs the Python dependencies used by the helper and notebook.
- `PROMPT.md` contains the standardized five-question agent prompt.
- `assets/` stores the generated outputs.

## Generated Outputs

- `assets/macro-snapshot.json`
- `assets/position-table.json`
- `assets/order-instructions.json`
- `assets/research-brief.md`
- `assets/agent-session.md`
- `assets/portfolio-summary.png`

## PolyBridge MCP

- Release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4
- Notebook: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb

## Dependencies

- Python 3.10+
- `requests`
- `pillow`
- Optional for the prompt workflow: Claude Desktop plus the PolyBridge MCP release above

## API Key Handling

Script mode expects `POLYBRIDGE_API_KEY` to already be present in the environment.

```bash
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
```

Notebook mode checks the environment first and only falls back to `getpass()` if the variable is missing. The key is never printed, saved into files, written into notebook outputs, or persisted into generated assets.

## Run Locally

From a fresh checkout:

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/longshort-portfolio
```

Or, if the repo already exists locally:

```bash
cd polybridge-cookbooks/longshort-portfolio
```

Then install dependencies, export your key, run portfolio sizing, and open the generated summary image:

```bash
bash setup.sh
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
python3 portfolio_sizing.py
open assets/portfolio-summary.png
```

## Notes

Cookbook outputs are market-implied examples from live Forecast calls. Values can change as source markets update.
