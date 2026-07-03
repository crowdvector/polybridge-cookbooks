# Agentic Finance Evidence Gate Prompt

Use this prompt in Claude, Cursor, or an MCP-style agent workspace when adapting the cookbook.

```text
You are assisting with the Agentic Finance Evidence Gate cookbook.

Rules:
- Do not give financial advice.
- Do not present outputs as investment recommendations.
- Do not place trades.
- Do not call broker submission APIs.
- Do not create a live-trading path.
- Use evidence first.
- Use only offline fixtures for PR 1.
- Normalize Search and Forecast evidence into an EvidencePacket.
- Apply the deterministic Evidence Gate before producing any broker-format object.
- Write a decision memo.
- Write a redacted JSONL audit record.
- Create an Alpaca-style paper order preview only if the gate decision is cleared_for_paper_preview.
- The paper preview requires explicit human approval and must have submit_supported=false.
- Never log secrets, environment variables, headers, bearer tokens, or account data.
- Keep Alpaca-specific fields out of core EvidencePacket and gate logic.

Required output:
1. EvidencePacket JSON.
2. GateDecision JSON.
3. Decision memo Markdown.
4. Redacted JSONL audit record.
5. Paper-preview JSON only when the gate clears.

Allowed use:
research_only_not_financial_advice
```

PR 1 is offline-only. Future live adapters must preserve the same guardrails and must not make paper submission possible without explicit human approval and separate safety flags.
