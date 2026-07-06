# Cursor Prompt

Copy this prompt into Cursor or a code-agent workspace opened at the repository root.

```text
You are working in crowdvector/polybridge-cookbooks.

Goal:
Run and inspect the Agentic Finance Evidence Gate cookbook without inventing evidence, outputs, test results, or file contents.

Safety invariants:
- Treat outputs as research/demo artifacts, not financial advice.
- Use evidence first.
- Do not call broker APIs except the guarded Alpaca paper runner when explicitly requested by the user.
- Do not submit live orders.
- Do not submit paper orders unless all guarded paper submission confirmations and checks pass.
- Do not create a real-money trading path.
- Do not provide portfolio-action instructions.
- Preserve EvidencePacket as the adapter boundary.
- Search relevance is not probability.
- Forecast is the probability surface.
- Memo and redacted audit output are required.
- Human approval is required before any broker-format paper-preview object can exist.

Offline checks:
Run:

PYENV_VERSION=3.13.0 python -m unittest discover agentic-finance/tests
PYENV_VERSION=3.13.0 python agentic-finance/tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
PYENV_VERSION=3.13.0 python agentic-finance/tier1_evidence_gate.py --thesis oil-shock-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
PYENV_VERSION=3.13.0 python agentic-finance/tier1_evidence_gate.py --thesis rates-fall-2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
PYENV_VERSION=3.13.0 python agentic-finance/run_portfolio_risk_map.py --offline --holdings agentic-finance/examples/sample_holdings.csv
PYENV_VERSION=3.13.0 python agentic-finance/tier3_alpaca_paper_trader.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json --preview-only

Inspect:
- agentic-finance/outputs/evidence-packet.json
- agentic-finance/outputs/decision-memo.md
- agentic-finance/outputs/portfolio-risk-map.json
- agentic-finance/outputs/portfolio-risk-memo.md
- agentic-finance/outputs/audit-log.jsonl

Optional live evidence:
- Run PYENV_VERSION=3.13.0 python agentic-finance/evidence_gate.py --live-polybridge only when the user explicitly asks.
- Run portfolio live mode only when the user explicitly asks.
- Live PolyBridge mode is read-only evidence retrieval. It must not create broker connectivity.

Optional Alpaca paper validation:
- Run PYENV_VERSION=3.13.0 python agentic-finance/run_alpaca_paper_check.py --validate-paper-account only when the user explicitly asks.
- Use paper credentials only and require APCA_API_BASE_URL=https://paper-api.alpaca.markets.
- Validation fetches sanitized account metadata only and must not submit orders.

Optional guarded Alpaca paper submission:
- Do not run this in quickstart checks or tests.
- Run PYENV_VERSION=3.13.0 python agentic-finance/tier3_alpaca_paper_trader.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json --submit-paper-order only when the user explicitly asks and provides all confirmation flags.
- Require --confirm-paper-trading, --confirm-not-financial-advice, and --confirm-human-approval.
- Use paper credentials only, require ALPACA_PAPER_TRADE=true, and require APCA_API_BASE_URL=https://paper-api.alpaca.markets.
- Confirm the Evidence Gate cleared before paper submission.
- Treat the result as simulated paper trading only, not financial advice and not live trading.

Review discipline:
- Report the actual command results.
- Read output files before summarizing them.
- Do not infer passing tests without running them.
- Do not fabricate PolyBridge Search or Forecast values.
- Do not persist raw PolyBridge responses, headers, secrets, account data, order IDs, or local absolute paths in committed files.
```
