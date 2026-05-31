# PolyBridge Long/Short Portfolio Prompt

Use this prompt in Claude Desktop with the PolyBridge MCP extension installed.

```text
You have access to the PolyBridge MCP tool.

My directional thesis:
- Short BERA: high token supply, no clear PMF, founder conviction signals low
- Short OP: declining sequencer revenue, ongoing token unlocks, fading narrative
- Long BTC: fixed supply, maximum decentralisation, actual PMF
- Uncertain WTI: geopolitics highly uncertain, need data before sizing
- Lean long SPX: AI tailwind structural but macro risks real

Use PolyBridge Forecast on exactly these five questions:
1. Will there be meaningful US crypto regulatory reform by Q2 2027?
2. Will the Fed cut rates before September 2026?
3. Will the US enter a recession by end of 2026?
4. Will the Strait of Hormuz reopen to regular traffic by June 30, 2026?
5. Will WTI crude oil exceed $90 in June 2026?

Portfolio constraints:
- Total notional budget: $50,000
- Notional USD sizing only
- Total absolute notional must stay less than or equal to $50,000
- No single position may exceed 40% of total notional
- WTI may be FLAT if the signal is mixed

Output format:
1. Macro read from the five PolyBridge results
2. Thesis challenges where market evidence argues against my view
3. Sized position table for BTC, SPX, OP, BERA, and WTI
4. Order instructions JSON

Order instruction requirements:
- Every order must include "asset"
- Every order must include "direction"
- Every order must include "notional_usd"
- Every order must include "target_notional_usd"
- Every order must include "units", if available, otherwise "not provided"
```
