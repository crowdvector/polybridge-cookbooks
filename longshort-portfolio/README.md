# Long-short portfolio on Hyperliquid from prediction market prices

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb)

An autonomous agent queries PolyBridge Forecast, reconstructs market-implied price distributions for five assets, and outputs a sized long-short portfolio for Hyperliquid 1x perps. Every direction and position size comes from prediction market data.

## Quick Links

- Article: https://polybridge.ai/research/longshort-portfolio
- Colab: https://colab.research.google.com/github/crowdvector/polybridge-cookbooks/blob/main/longshort-portfolio/longshort-portfolio.ipynb
- GitHub folder: https://github.com/crowdvector/polybridge-cookbooks/tree/main/longshort-portfolio
- PolyBridge MCP release: https://github.com/crowdvector/polybridge-search-mcp/releases/tag/polybridge-mcp-v0.2.4

## What This Cookbook Builds

This cookbook replaces the old macro view workflow with a price-threshold workflow:

- asks four Forecast price-threshold questions for each of `BTC`, `SPX`, `OP`, `BERA`, and `WTI`
- makes 20 Forecast calls total for the July 31, 2026 horizon
- rounds thresholds from spot prices using 0.60, 0.85, 1.15, and 1.50 factors
- enforces monotonic survival probabilities so higher thresholds cannot have higher clipped probability
- reconstructs a piecewise price distribution from the survival curve
- computes expected return and implied vol for each asset
- sizes positions with half-Kelly under a $50,000 budget and a $20,000 single-position cap
- writes Hyperliquid 1x perp order instructions as JSON

The script never places orders. It only writes order instructions.

## Method

Each survival probability `P(price > T)` is a point on the asset's implied cumulative distribution. Four thresholds define five probability bands:

- Below `T1`: probability `1 - P(> T1)`, midpoint `T1 / 2`
- Between thresholds: probability `P(> Ti) - P(> Ti+1)`, midpoint `(Ti + Ti+1) / 2`
- Above `T4`: probability `P(> T4)`, midpoint `(T4 + 1.5 * T4) / 2`

The expected price is the probability-weighted sum of band midpoints. Expected return is `(E[price] - spot) / spot`, and implied vol is the band-price standard deviation divided by spot. The half-Kelly weight is:

```text
weight = 0.5 * E[return] / Vol^2
```

The workflow caps each signed position at 40% of the $50,000 budget, scales proportionally if gross notional exceeds the budget, and rounds final notional to the nearest $100.

## Example Snapshot

The public example uses the May 31, 2026 article snapshot. Live runs can differ as source markets update.

```text
Asset  Dir     E[r]     Vol    Notional
------------------------------------------
BTC    LONG   +6.40%  33.70%    $8,600
SPX    LONG   +7.86%  23.30%   $12,200
OP     SHORT  -6.00%  31.90%    $9,000
BERA   SHORT -11.05%  30.00%   $12,200
WTI    LONG   +2.78%  23.00%    $8,000

Gross: $50,000 / $50,000
```

The example order instructions are in `assets/order-instructions.json`.

## Files

- `portfolio.py` runs the reproducible REST-backed workflow and writes JSON assets.
- `longshort-portfolio.ipynb` runs the same helper from notebook mode.
- `PROMPT.md` contains the canonical PolyBridge MCP prompt.
- `setup.sh` installs the minimal Python dependency.
- `assets/` stores public example JSON outputs.

## Generated Outputs

- `assets/survival-probabilities.json`
- `assets/sizing-table.json`
- `assets/order-instructions.json`

## Dependencies

- Python 3.10+
- `requests`
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

```bash
git clone https://github.com/crowdvector/polybridge-cookbooks.git
cd polybridge-cookbooks/longshort-portfolio
bash setup.sh
read -s "POLYBRIDGE_API_KEY?Paste POLYBRIDGE_API_KEY: "
echo
export POLYBRIDGE_API_KEY
python3 portfolio.py
```

The script prints the survival probability table, the expected return / implied vol / sizing table, gross notional, and the Hyperliquid 1x perp order instructions JSON. It also writes the three JSON assets into `assets/`.

## Limitations

This is a market-implied example, not financial advice. Positions are sized independently and ignore cross-asset correlation. The upper-tail ceiling is a modeling assumption. Four thresholds give a coarse distribution. Prediction market prices are risk-neutral, can be thin, and may come from weak proxy markets. If raw survival probabilities are non-monotonic, clipping makes the arithmetic coherent but does not make the underlying signal reliable.
