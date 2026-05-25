# PolyBridge Cookbooks

Runnable examples for building with PolyBridge Search, Forecast, and MCP.

Each cookbook is designed to be self-contained:

- `README.md` explains the recipe.
- `.ipynb` runs in Google Colab.
- `setup.sh` installs local dependencies.
- `PROMPT.md` gives agents enough context to reproduce or adapt the example.
- `assets/` stores generated charts, screenshots, and snapshot outputs.

## Cookbooks

| Cookbook | Status | Description |
|---|---|---|
| `vix-forecast/` | Draft | Forecast VIX and market stress from prediction markets. |
| `portfolio-allocation/` | Draft | Use market-implied probabilities in an asset allocation workflow. |
| `longshort-portfolio/` | Draft | Use PolyBridge MCP with Claude to size a dry-run long/short portfolio. |

## Requirements

Most examples use a PolyBridge API key with Forecast access.

Create a key in the Developer Console:

https://polybridge.ai/console

Set it locally:

```bash
read -s POLYBRIDGE_API_KEY
export POLYBRIDGE_API_KEY
```

Do not commit API keys or secrets.

## Disclaimer

These cookbooks are technical examples. They are not financial advice.
Outputs are market-implied snapshots and can change as markets update.
