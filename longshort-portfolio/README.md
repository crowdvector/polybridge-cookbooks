# Long/Short MCP Dry-Run Portfolio

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb)

Use PolyBridge Forecast probabilities to turn a directional long/short thesis into a dry-run, review-only portfolio demo across `BTC`, `SPX`, `OP`, `BERA`, and optionally `WTI`.

The Colab link above is the final public path. It will work after `crowdvector/polybridge-cookbooks` is published and this repo is pushed there.

## What This Cookbook Builds

This cookbook:

- asks the same five macro questions that power the PolyBridge long/short demo
- keeps the workflow dry-run and review-only by default
- generates a reproducible macro snapshot from `POST https://api.polybridge.ai/v1/forecast`
- applies a transparent sizing heuristic to the user thesis with a total notional cap of `$50,000`
- writes structured JSON and markdown assets for the later website article
- never places trades, never requests Hyperliquid private keys, and never instantiates execution clients

## Claude/MCP vs REST Helper

There are two workflows in this cookbook:

- `PROMPT.md` is the interactive Claude Desktop + PolyBridge MCP workflow. It is for exploratory agent use, thesis challenges, and conversational review.
- `dry_run_portfolio.py` is the reproducible REST-backed helper. It calls the Forecast endpoint sequentially, retries `429` and `503` with `Retry-After`, sanitizes the responses, and writes the dry-run assets used in this cookbook.

Both paths are review-only. Neither path should submit trades, call execution APIs, or rely on Hyperliquid private keys.

## Files

- `dry_run_portfolio.py` runs the reproducible long/short dry run and writes the article assets.
- `longshort-portfolio.ipynb` explains the Claude/MCP setup and runs the REST-backed helper from notebook mode.
- `setup.sh` installs the Python dependencies used by the helper and notebook.
- `PROMPT.md` contains the standardized five-question agent prompt.
- `assets/` stores the generated dry-run outputs.

## Generated Outputs

- `assets/macro-snapshot.json`
- `assets/position-table.json`
- `assets/review-only-orders.json`
- `assets/research-brief.md`
- `assets/agent-session.md`
- `assets/dry-run-summary.png`

## PolyBridge MCP

- Release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4
- Future notebook path: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb

## API Key Handling

Script mode expects `POLYBRIDGE_API_KEY` to already be present in the environment.

Notebook mode checks the environment first and only falls back to `getpass()` if the variable is missing. The key is never printed, saved into files, written into notebook outputs, or persisted into generated assets.

## Run Locally

Install dependencies:

```bash
./longshort-portfolio/setup.sh
```

Run the dry-run helper:

```bash
python3 longshort-portfolio/dry_run_portfolio.py
```

## Notes

This cookbook is dry-run only, review-only, and not financial advice. Generated order JSON is intentionally non-executable and exists solely for human review of notional intent.
