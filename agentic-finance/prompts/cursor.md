# Cursor Prompt

Copy this prompt into Cursor or a code-agent workspace opened at the repository root.

```text
You are working in crowdvector/polybridge-cookbooks.

Goal:
Run and inspect the Agentic Finance Evidence Gate cookbook without inventing evidence, outputs, test results, or file contents.

Safety invariants:
- Treat outputs as research/demo artifacts, not financial advice.
- Use evidence first.
- Do not call broker APIs.
- Do not submit orders.
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
PYENV_VERSION=3.13.0 python agentic-finance/evidence_gate.py --offline
PYENV_VERSION=3.13.0 python agentic-finance/run_portfolio_risk_map.py --offline --holdings agentic-finance/examples/sample_holdings.csv
PYENV_VERSION=3.13.0 python agentic-finance/run_alpaca_paper_check.py --preview-only

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

Review discipline:
- Report the actual command results.
- Read output files before summarizing them.
- Do not infer passing tests without running them.
- Do not fabricate PolyBridge Search or Forecast values.
- Do not persist raw PolyBridge responses, headers, secrets, account data, order IDs, or local absolute paths in committed files.
```
