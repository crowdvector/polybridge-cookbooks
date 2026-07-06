# Cursor Prompt

Copy this prompt into Cursor or another code-agent workspace opened at the repository root.

```text
You are working in crowdvector/polybridge-cookbooks.

Goal:
Run and inspect the Market Foresight Before Trading cookbook without inventing evidence, outputs, test results, or file contents.

Safety:
- This is research/demo software, not financial advice.
- Do not place real trades.
- Do not connect to real brokerage accounts.
- Do not create a real-money trading path.
- Use replay mode by default.
- Use SimBroker only for local simulated paper-trade recording.
- Human confirmation is required before any simulated fill.
- Search relevance is not probability.
- Forecast is the probability surface.
- Memo and redacted audit output are required.

Run:

PYENV_VERSION=3.13.0 python -m unittest discover agentic-finance/tests
PYENV_VERSION=3.13.0 python agentic-finance/tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json
printf "y\n" | PYENV_VERSION=3.13.0 python agentic-finance/tier3_paper_trader.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json

Inspect:
- agentic-finance/outputs/decision-memo.md
- agentic-finance/outputs/decisions.jsonl
- agentic-finance/outputs/paper_portfolio.jsonl

Report actual command results. Do not fabricate PolyBridge probabilities or simulated broker output.
```
