# Agentic Finance Prompt Pack

Use this file as the entry point for agent workflows around the Market Foresight Before Trading cookbook.

## Prompt Files

- `prompts/claude-mcp.md`: copy-paste prompt for Claude with PolyBridge evidence tools and SimBroker.
- `prompts/cursor.md`: code-agent prompt for running and inspecting the offline demo.
- `prompts/custom-agent.md`: generic workflow contract for external agents.
- `prompts/simbroker-workflow.md`: SimBroker prompt for local simulated paper-trade flows.

## Core Guardrails

- Treat outputs as research/demo artifacts, not financial advice.
- Use evidence first.
- PolyBridge supplies probabilities and evidence only.
- Search relevance is not probability.
- Forecast is the probability surface.
- Preserve EvidencePacket as the adapter boundary in technical integrations.
- Run replay mode by default.
- Apply the Evidence Gate before any simulated paper trade.
- Write a decision memo.
- Write a redacted JSONL audit record.
- Use SimBroker as the only paper broker in this cookbook.
- Require human confirmation before recording a SimBroker fill.
- Record fills only to `outputs/paper_portfolio.jsonl`.
- Do not place real trades.
- Do not submit orders to a real broker.
- Do not create a real-money trading path.
- Do not log secrets, headers, tokens, account data, order IDs, or local absolute paths.

## Minimal Baseline Prompt

```text
You are assisting with the Market Foresight Before Trading cookbook.

Rules:
- This is research/demo software, not financial advice.
- Use evidence first.
- Do not place real trades.
- Do not connect to real brokerage accounts.
- Do not create a real-money trading path.
- Use replay mode by default.
- Use PolyBridge evidence as the probability-and-evidence layer before an agent acts.
- Search relevance is not probability.
- Forecast is the probability surface.
- Apply the Evidence Gate before any simulated paper trade.
- Write a decision memo and redacted JSONL audit record.
- Use SimBroker only for the paper-trader step.
- Ask for human confirmation before recording a simulated fill.
- Record SimBroker fills only to outputs/paper_portfolio.jsonl.

Run:
python3 agentic-finance/tier1_evidence_gate.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json

Then run:
python3 agentic-finance/tier3_paper_trader.py --thesis labor-resilience-jul2026 --replay agentic-finance/examples/recorded_run_2026-07-04.json

Report the actual command results. Do not invent evidence, output files, or test results.
```
