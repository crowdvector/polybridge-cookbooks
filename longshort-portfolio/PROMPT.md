# Long-short Portfolio Prompt

Use this prompt in Claude Desktop with the PolyBridge MCP tool connected.

```text
You have access to the PolyBridge MCP tool (polybridge_forecast).

Assets and spot prices:
BTC $74,000 · SPX $7,580 · OP $0.12 · BERA $0.38 · WTI $87

For each asset, query PolyBridge Forecast at four price thresholds
(0.60x, 0.85x, 1.15x, 1.50x spot), all resolving July 31, 2026.

Round thresholds: to nearest $100 if spot >= $1,000; to nearest $1
if spot >= $10; to nearest $0.01 otherwise.

Question format: "Will {ASSET} exceed ${T} on July 31, 2026?"

Collect all 20 probabilities first. Then write and execute a Python
script that:

1. Enforces monotonicity (clip so P(> T_i+1) <= P(> T_i)).

2. Reconstructs a piecewise price distribution per asset:
   Below T1:              prob = 1 - P(> T1),             midpoint = T1 / 2
   Between Ti and Ti+1:   prob = P(> Ti) - P(> Ti+1),     midpoint = (Ti + Ti+1) / 2
   Above T4:              prob = P(> T4),                 midpoint = (T4 + 1.5 * T4) / 2

3. Computes per asset:
   E[price]  = sum(midpoint * prob)
   E[return] = (E[price] - spot) / spot
   Vol       = sqrt(sum(midpoint^2 * prob) - E[price]^2) / spot

4. Sizes via half-Kelly:
   weight   = 0.5 * E[return] / Vol^2
   notional = weight * $50,000

   Constraints:
   Gross notional <= $50,000
   No single position > $20,000 (40%)
   Scale all positions proportionally if gross exceeds budget
   Round to nearest $100
   Direction = sign of E[return]

Output:
1. Survival probability table per asset
2. Expected returns, implied vols, and sized position table
3. Hyperliquid 1x perp order instructions as JSON
```

Notes:

- Update spot prices before running.
- Collect all 20 Forecast probabilities before running sizing.
- If raw probabilities are non-monotonic, clip for arithmetic coherence and report that clipping occurred.
- Source counts should be derived from `markets_used` when using REST responses; do not assume a direct source-count field is always present.
